import time

from django.core.management.base import BaseCommand

from offline_exam.sync import process_due_outbox


class Command(BaseCommand):
    help = "Upload pending local CBT submissions; use --loop for a simple polling worker."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=int, default=30)

    def handle(self, *args, **options):
        while True:
            result = process_due_outbox()
            self.stdout.write(str(result))
            if not options["loop"]:
                return
            time.sleep(max(5, options["interval"]))
