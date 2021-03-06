#! /usr/bin/python3.4

from redis import StrictRedis
from bson import Binary
import pickle
import argparse
import logging
import logging.handlers
import sys

import dbops

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='LiArchiver .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    FILESIZE=1024*1024*1024 #1MB
    handler=('LI ARCHIVER-['+instance+']')
    formatter = ('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)

    logger = logging.getLogger('liarchiver'+instance)
    rclient = StrictRedis()

    liarchivebackup = 'liarchivebackup_'+instance

    db = dbops.MongoORM()
    while True:
        if (rclient.llen(liarchivebackup)):
            item = rclient.brpop (liarchivebackup)
            logger.info("Getting Mails from {}".format(liarchivebackup))
            itemlist = pickle.loads(item[1])
            if (len(itemlist) == 2):
                db.lidump(itemlist, Binary(str(itemlist[1]).encode(), 128))
        else:
            item = rclient.brpoplpush('liarchive', liarchivebackup)
            itemlist = pickle.loads(item)
            if (len(itemlist) == 2):
                db.lidump(itemlist, Binary(str(itemlist[1]).encode(), 128))
            logger.info ('len of {} is : {}'.format(liarchivebackup, rclient.llen(liarchivebackup)))
            rclient.lrem(liarchivebackup, 0, item)
            logger.info ('len of {} is : {}'.format(liarchivebackup, rclient.llen(liarchivebackup)))
