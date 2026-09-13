import time

from src.runtime.scheduler import BackgroundScheduler


scheduler = BackgroundScheduler(
    interval_seconds=10
)

print("Starting scheduler...")

scheduler.start()

try:
    time.sleep(35)

finally:
    print("Stopping scheduler...")
    scheduler.stop()