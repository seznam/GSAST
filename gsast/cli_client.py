import click
import json
import os
import requests
import glob
from urllib.parse import urlencode
from models.config_models import GSASTConfig, ProviderType, TargetConfig, FiltersConfig, ScannerType

DEFAULT_CONFIG_FILE_PATH = os.path.join(os.path.expanduser('~'), '.gsast.json')


def create_default_config(config_path: str):
    with open(config_path, 'w') as config_file:
        # Create default configuration in new format
        default_config = {
            'api_secret_key': 'CHANGE_ME',
            'base_url': 'http://localhost:5000',
            'target': {
                'provider': 'github',
                'organizations': ['seznam'],
                'repositories': []
            },
            'filters': {
                'is_archived': True,
                'is_fork': True,
                'is_personal_project': True,
                'max_repo_mb_size': 500,
                'ignore_path_regexes': [],
                'must_path_regexes': [],
                'last_commit_max_age': 365,
            },
            'scanners': ['semgrep'],
        }
        json.dump(default_config, config_file, indent=4)

def ensure_config_file_exists(config_path: str):
    """Ensure configuration file exists, creating it if necessary."""
    if not os.path.exists(config_path):
        # Create directory if it doesn't exist (for custom config paths)
        config_dir = os.path.dirname(config_path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        create_default_config(config_path)

        click.secho(f"Configuration file created at {config_path}.", fg='yellow')
        click.secho("Please update the configuration with your provider details, API keys, and organizations/groups.", fg='yellow')
        return False
    return True


def load_config(config_path: str = None):
    """Load and validate configuration from file."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_FILE_PATH
    
    # Ensure config file exists
    if not ensure_config_file_exists(config_path):
        click.secho("Configuration file was created. Please update it with your settings before running scan.", fg='yellow')
        raise click.ClickException("Configuration file needs to be updated")
    
    try:
        config = GSASTConfig.from_json_file(config_path)
        click.secho(f"Configuration loaded successfully from {config_path}", fg='green')
        return config
    except FileNotFoundError:
        click.secho(f"Configuration file not found: {config_path}", fg='red')
        raise click.ClickException(f"Configuration file not found: {config_path}")
    except ValueError as e:
        click.secho(f"Invalid configuration: {e}", fg='red')
        click.secho(f"Please check your configuration file at {config_path}", fg='red')
        raise click.ClickException(f"Invalid configuration: {e}")
    except Exception as e:
        click.secho(f"Error loading configuration: {e}", fg='red')
        click.secho(f"Please check your configuration file at {config_path}", fg='red')
        raise click.ClickException(f"Error loading configuration: {e}")


def build_config_from_args(cli_args, base_config: GSASTConfig):
    """Build config structure from CLI arguments and base config."""
    # Start with base config values
    config_dict = {
        'api_secret_key': base_config.api_secret_key,
        'base_url': base_config.base_url,
        'target': base_config.target.to_dict() if base_config.target else {'provider': 'github'},
        'scanners': base_config.scanners or ['semgrep']
    }
    
    # Build filters from CLI args, falling back to base config
    filters_dict = {}
    if base_config.filters:
        filters_dict = base_config.filters.to_dict()
    
    # Override with CLI args if provided
    filter_mappings = {
        'is_archived': 'is_archived',
        'is_fork': 'is_fork', 
        'is_personal_project': 'is_personal_project',
        'max_repo_mb_size': 'max_repo_mb_size',
        'ignore_path_regexes': 'ignore_path_regexes',
        'must_path_regexes': 'must_path_regexes',
        'last_commit_max_age': 'last_commit_max_age'
    }
    
    for cli_key, config_key in filter_mappings.items():
        if cli_args.get(cli_key) is not None:
            filters_dict[config_key] = cli_args[cli_key]
    
    if filters_dict:
        config_dict['filters'] = filters_dict
    
    # Handle GitLab-specific group arguments
    if cli_args.get('group_ids'):
        if 'target' not in config_dict:
            config_dict['target'] = {}
        config_dict['target']['groups'] = cli_args['group_ids']
        config_dict['target']['provider'] = 'gitlab'  # Set provider to gitlab if groups specified
    
    if cli_args.get('group_with_shared') is not None:
        if 'target' not in config_dict:
            config_dict['target'] = {}
        config_dict['target']['group_with_shared'] = cli_args['group_with_shared']
    
    if cli_args.get('group_include_subgroups') is not None:
        if 'target' not in config_dict:
            config_dict['target'] = {}
        config_dict['target']['group_include_subgroups'] = cli_args['group_include_subgroups']
    
    # Handle scan_secrets if provided
    if cli_args.get('scan_secrets') is not None:
        config_dict['scan_secrets'] = cli_args['scan_secrets']
    
    return GSASTConfig.from_dict(config_dict)


# Split comma-separated values into lists for specific CLI arguments
def split_comma_list_args(cli_args, comma_keys):
    for key in comma_keys:
        if key in cli_args and cli_args[key]:
            cli_args[key] = [item.strip() for item in cli_args[key][0].split(',')]

def execute_api_request(method, endpoint, config: GSASTConfig, data=None):
    headers = {'API-SECRET-KEY': config.api_secret_key}
    url = f"{config.base_url}{endpoint}"

    if method.upper() == 'POST':
        response = requests.post(url, json=data, headers=headers)
    elif method.upper() == 'GET':
        response = requests.get(url, headers=headers)
    elif method.upper() == 'DELETE':
        response = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"HTTP method {method} not supported.")

    # Pretty-print JSON when possible, fall back to text
    if response.ok:
        try:
            parsed = response.json()
            click.secho(json.dumps(parsed, indent=2, ensure_ascii=False), fg='green')
        except ValueError:
            # Not JSON
            click.secho(response.text, fg='green')
    else:
        try:
            parsed_err = response.json()
            click.secho(json.dumps(parsed_err, indent=2, ensure_ascii=False), fg='red')
        except ValueError:
            click.secho(f"Error: {response.status_code} {response.reason}", fg='red')
            if response.text:
                click.secho(response.text, fg='red')
    return response


@click.group()
@click.option('--config', '-c', 
              type=click.Path(exists=False), 
              default=None,
              help=f'Path to configuration file (default: {DEFAULT_CONFIG_FILE_PATH})')
@click.pass_context
def cli(ctx, config):
    """Global SAST scanning tool CLI."""
    # Ensure that ctx.obj exists and is a dict (will be used to pass data between commands)
    ctx.ensure_object(dict)
    
    # Store the config path for use by subcommands
    ctx.obj['config_path'] = config if config else DEFAULT_CONFIG_FILE_PATH


@cli.command()
@click.argument('rules', nargs=-1, type=click.Path(exists=True), required=False)
@click.option('--is-archived', type=bool, help='Filter out archived projects from scan')
@click.option('--is-fork', type=bool, help='Filter out forked projects from scan')
@click.option('--is-personal-project', type=bool, help='Filter out personal projects from scan')
@click.option('--max-repo-mb-size', type=int, help='Maximum repository size in MB to be included in scan')
@click.option('--ignore-path-regexes', multiple=True, type=str, help='Path regexes to be excluded from scan separated by comma')
@click.option('--must-path-regexes', multiple=True, type=str, help='Path regexes to be included in scan separated by comma')
@click.option('--group-ids', multiple=True, type=str, help='Group IDs to which projects should belong separated by comma')
@click.option('--group-with-shared', type=bool, help='Include projects shared with specified group IDs')
@click.option('--group-include-subgroups', type=bool, help='Include projects in subgroups of specified group IDs')
@click.option('--scan-secrets', type=bool, help='Scan for hardcoded secrets in the git history using Trufflehog, note that this slows down git clone')
@click.option('--last-commit-max-age', type=int, help='Filter out projects with last commit time older than specified number of days')
@click.pass_context
def scan(ctx, rules, **cli_args):
    config_path = ctx.obj['config_path']
    base_config = load_config(config_path)
    split_comma_list_args(cli_args, ['ignore_path_regexes', 'must_path_regexes', 'group_ids'])
    final_config = build_config_from_args(cli_args, base_config)

    # Check if semgrep scanner is enabled and rules are required
    semgrep_enabled = final_config.scanners and ScannerType.SEMGREP in final_config.scanners
    
    if semgrep_enabled and not rules:
        click.secho("Error: Rules are required when 'semgrep' scanner is enabled in the configuration.", fg='red')
        click.secho("Please provide rule files/directories as arguments or remove 'semgrep' from scanners list.", fg='red')
        raise click.ClickException("Rules are required for semgrep scanner")
    
    if not semgrep_enabled and rules:
        click.secho("Warning: Rules provided but 'semgrep' scanner is not enabled in configuration. Rules will be ignored.", fg='yellow')

    rule_files = []
    if semgrep_enabled and rules:
        rule_extensions = ('.yaml', '.yml', '.json')
        for rule_path in rules:
            if os.path.isdir(rule_path):
                pattern = os.path.join(rule_path, '**', '*')
                rule_files.extend([
                    {'name': os.path.basename(rule_file), 'content': open(rule_file).read()}
                    for rule_file in glob.glob(pattern, recursive=True)
                    if os.path.isfile(rule_file) and rule_file.lower().endswith(rule_extensions)
                ])
            elif os.path.isfile(rule_path) and rule_path.lower().endswith(rule_extensions):
                rule_files.append({'name': os.path.basename(rule_path), 'content': open(rule_path).read()})
        
        if not rule_files:
            click.secho("Error: No valid rule files found in the provided paths.", fg='red')
            raise click.ClickException("No valid rule files found")
        
        click.secho(f"Loaded {len(rule_files)} rule files for semgrep scanner.", fg='green')

    # Build the data payload using the new structured format
    data = {
        'config': final_config.to_dict(),  # Send the entire structured config
        'rule_files': rule_files
    }
    execute_api_request('POST', '/scan', final_config, data=data)


@cli.command()
@click.argument('scan_id')
@click.pass_context
def info(ctx, scan_id):
    config_path = ctx.obj['config_path']
    config = load_config(config_path)
    execute_api_request('GET', f'/scan/{scan_id}/status', config)


@cli.command('scans-status')
@click.pass_context
def scans_status(ctx):
    """Get status of all scans."""
    config_path = ctx.obj['config_path']
    config = load_config(config_path)
    execute_api_request('GET', '/queue/scans', config)


@cli.command()
@click.argument('scan_id')
@click.option('--query', type=str, help='JSONPath query to extract specific data from SARIF results')
@click.option('--project', type=str, help='Filter results by project name/URL')  
@click.option('--scan', type=str, help='Filter results by scanner type (e.g., dependency-confusion, semgrep)')
@click.pass_context
def results(ctx, scan_id, query, project, scan):
    config_path = ctx.obj['config_path']
    config = load_config(config_path)
    
    # Build query parameters
    params = {}
    if query:
        params['query'] = query
    if project:
        params['project'] = project
    if scan:
        params['scan'] = scan
    
    endpoint = f'/scan/{scan_id}/results'
    if params:
        endpoint += '?' + urlencode(params)
    
    execute_api_request('GET', endpoint, config)

@cli.command()
@click.pass_context
def cleanup_queues(ctx):
    config_path = ctx.obj['config_path']
    config = load_config(config_path)
    execute_api_request('DELETE', '/queue/cleanup', config)


@cli.command()
@click.pass_context
def cleanup_projects(ctx):
    config_path = ctx.obj['config_path']
    config = load_config(config_path)
    execute_api_request('DELETE', '/queue/projects', config)


if __name__ == '__main__':
    cli()
