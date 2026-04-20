from rq import Worker

from gsast_worker.tasks import main_cli


def wait_for_tasks():
    scans_redis, tasks_redis, tasks_queue, rules_redis, unified_project_downloader, sast_ruleset_downloader, args = main_cli()
    tasks_queue_worker = Worker([tasks_queue], connection=tasks_redis)
    tasks_queue_worker.work()


def main():
    wait_for_tasks()


if __name__ == '__main__':
    main()
