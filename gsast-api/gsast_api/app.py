from flasgger import Swagger
from flask import Flask, g

from gsast_api import infra
from gsast_api.routes.admin_routes import admin_bp
from gsast_api.routes.result_routes import result_bp
from gsast_api.routes.scan_routes import scan_bp
from gsast_api.services.scanner_service import ScannerService


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)
    Swagger(app)

    app.register_blueprint(scan_bp)
    app.register_blueprint(result_bp)
    app.register_blueprint(admin_bp)

    return app


def init_app(app: Flask) -> None:
    """Parse CLI args / env vars, wire up Redis connections, and attach a before_request hook."""
    cli_args = infra.parse_args()

    redis_scans, _, tasks_queue, redis_rules, redis_projects = infra.setup_redis(cli_args.redis_url)

    app.config.update(
        REDIS_SCANS=redis_scans,
        REDIS_TASKS=tasks_queue,
        REDIS_RULES=redis_rules,
        REDIS_PROJECTS=redis_projects,
        GITLAB_URL=cli_args.gitlab_url,
        GITLAB_API_TOKEN=cli_args.gitlab_api_token,
        GITHUB_API_TOKEN=cli_args.github_api_token,
        API_SECRET_KEY=cli_args.api_secret_key,
        SCANNER_SERVICE=ScannerService(),
    )

    @app.before_request
    def _inject_globals():
        g.redis_scans = app.config['REDIS_SCANS']
        g.redis_tasks = app.config['REDIS_TASKS']
        g.redis_rules = app.config['REDIS_RULES']
        g.redis_projects = app.config['REDIS_PROJECTS']
        g.gitlab_url = app.config['GITLAB_URL']
        g.GITLAB_API_TOKEN = app.config['GITLAB_API_TOKEN']
        g.GITHUB_API_TOKEN = app.config['GITHUB_API_TOKEN']
        g.API_SECRET_KEY = app.config['API_SECRET_KEY']


def main() -> None:
    app = create_app()
    init_app(app)
    app.run(host='0.0.0.0', port=5000)


if __name__ == '__main__':
    main()
