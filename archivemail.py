#! /usr/bin/python3.4

from redis import StrictRedis
from bson import Binary
import pymongo
import pickle
import argparse
import logging
import logging.handlers
import datetime

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Archiver .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    FILESIZE=1024*1024*1024 #1MB
    logger = logging.getLogger('emailarchiver'+instance)
    formatter = logging.Formatter('EMAIL ARCHIVER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
    hdlr = logging.handlers.RotatingFileHandler('/var/tmp/emailarchiver_'+instance+'.log', maxBytes=FILESIZE, backupCount=10)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

    try:
        conn=pymongo.MongoClient()
        print ("Connected successfully!!!")
    except pymongo.errors.ConnectionFailure as e:
        print ("Could not connect to MongoDB: %s" % e )

    db = conn.inbounddb.mailBackup

    db.ensure_index("Expiry_date", expireAfterSeconds=0)

    rclient = StrictRedis()

    mailarchivebackup = 'mailarchivebackup_' + instance
    while True:
        if (rclient.llen(mailarchivebackup)):
            item = rclient.brpop (mailarchivebackup)
            message = pickle.loads (item[1])
            logger.info("Getting Mails from {}".format(mailarchivebackup))
            utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
            db.insert( {'from':message['msg']['from_email'], 'Expiry_date' : utc_timestamp, 'inboundJson':Binary(str(message).encode(), 128)} )
        else:
            item = rclient.brpoplpush('mailarchive', mailarchivebackup)
            message = pickle.loads(item)
            logger.info("Getting Mails from {}".format('mailarchive'))
            utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
            db.insert( {'from':message['msg']['from_email'], 'Expiry_date' : utc_timestamp, 'inboundJson':Binary(str(message).encode(), 128)} )
            logger.info ('len of {} is : {}'.format(mailarchivebackup, rclient.llen(mailarchivebackup)))
            rclient.lrem(mailarchivebackup, 0, item)
            logger.info ('len of {} is : {}'.format(mailarchivebackup, rclient.llen(mailarchivebackup)))
