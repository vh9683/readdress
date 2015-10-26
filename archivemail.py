#! /usr/bin/python3.4

import argparse
import datetime
import logging
import logging.handlers
import pickle
import sys

from redis import StrictRedis
import dbops

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Archiver .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    FILESIZE=1024*1024*1024 #1MB
    handler = ('EMAIL ARCHIVER-['+instance+']')
    formatter = ('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
    logger = logging.getLogger('emailarchiver'+instance)

    rclient = StrictRedis()
    mailarchivebackup = 'mailarchivebackup_' + instance

    db = dbops.MongoORM()
    logger.info("Starting email archiver")

    while True:
        if (rclient.llen(mailarchivebackup)):
            item = rclient.brpop (mailarchivebackup)
            message = pickle.loads (item[1])
            logger.info("Getting Mails from {}".format(mailarchivebackup))
            utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
            db.dumpmail(message)
        else:
            item = rclient.brpoplpush('mailarchive', mailarchivebackup)
            message = pickle.loads(item)
            logger.info("Getting Mails from {}".format('mailarchive'))
            db.dumpmail(message)
            logger.info ('len of {} is : {}'.format(mailarchivebackup, rclient.llen(mailarchivebackup)))
            rclient.lrem(mailarchivebackup, 0, item)
            logger.info ('len of {} is : {}'.format(mailarchivebackup, rclient.llen(mailarchivebackup)))
