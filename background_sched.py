import datetime
import time
import os
import logging
import logging.handlers
import sys
from initiate_verification import start_verification_suspension
from initiate_verification import fetch_users_records

from apscheduler.schedulers.background import BackgroundScheduler

handler='background-scheduler['+'0'+']'
formatter=('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
logger = logging.getLogger('bg_scheduler')


def verify_suspend_job():
    times = datetime.datetime.now()
    verify_recs, suspend_recs = fetch_users_records()
    if len(verify_recs) or len(suspend_recs):
        logging.info( "starting verify_suspend_job @:{}\n".format(times) )
        start_verification_suspension(verify_recs, suspend_recs)
    else:
        logger.error("No Records to Verify @:{}".format(times))



if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    startDate = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1),datetime.time(1))
    scheduler.add_job(verify_suspend_job, 'interval', days=1, next_run_time=startDate, misfire_grace_time=60)
    scheduler.start()
    print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()  # Not strictly necessary if daemonic mode is enabled but should be done if possible

