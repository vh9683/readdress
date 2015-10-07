#! /usr/bin/python3.4

from redis import StrictRedis
from bson import Binary
import pymongo
import pickle
import argparse
import logging
import logging.handlers


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LiArchiver .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    FILESIZE=1024*1024*1024 #1MB
    logger = logging.getLogger('liarchiver'+instance)
    formatter = logging.Formatter('LI ARCHIVER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
    hdlr = logging.handlers.RotatingFileHandler('/var/tmp/liarchiver_'+instance+'.log', maxBytes=FILESIZE, backupCount=10)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

    try:
        conn=pymongo.MongoClient()
        print ("Connected successfully!!!")
    except pymongo.errors.ConnectionFailure as e:
        print ("Could not connect to MongoDB: %s" % e )

    db = conn.inbounddb.liMailBackUp
    rclient = StrictRedis()

    liarchivebackup = 'liarchivebackup_'+instance
    while True:
        if (rclient.llen(liarchivebackup)):
            item = rclient.brpop (liarchivebackup)
            logger.info("Getting Mails from {}".format(liarchivebackup))
            itemlist = pickle.loads(item[1])
            if (len(itemlist) == 2):
                db.insert( { 'tagged':itemlist[0], 'inboundJson':Binary(str(itemlist[1]).encode(), 128)} )
        else:
            item = rclient.brpoplpush('liarchive', liarchivebackup)
            itemlist = pickle.loads(item)
            if (len(itemlist) == 2):
                db.insert( { 'tagged':itemlist[0], 'inboundJson':Binary(str(itemlist[1]).encode(), 128)} )
            logger.info ('len of {} is : {}'.format(liarchivebackup, rclient.llen(liarchivebackup)))
            rclient.lrem(liarchivebackup, 0, item)
            logger.info ('len of {} is : {}'.format(liarchivebackup, rclient.llen(liarchivebackup)))
