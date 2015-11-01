import datetime
import time
import os

from apscheduler.schedulers.background import BackgroundScheduler


def tick():
    times = datetime.datetime.now()
    t = "time {}".format(times)
    cmd = 'mail -s \"{0}\" badari.hp@gmail.com < /tmp/.gmail'.format(t)
    os.system(cmd)
    cmd = 'mail -s \"{0}\" harish.v.murthy@gmail.com < /tmp/.gmail'.format(t)
    os.system(cmd)


if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    startDate = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1),datetime.time(1))
    scheduler.add_job(tick, 'interval', days=1, next_run_time=startDate)
    scheduler.start()
    print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()  # Not strictly necessary if daemonic mode is enabled but should be done if possible

