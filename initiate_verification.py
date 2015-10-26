#! /usr/bin/python3.4

import argparse
import copy
import email.utils
import json
import logging
import logging.handlers
import pickle
import re
import sys
import uuid
from email.utils import parseaddr

from redis import StrictRedis
from validate_email import validate_email
import asyncio

import dbops
import validations

OUR_DOMAIN = 'readdress.io'
logger = logging.getLogger('phone_verification_handler')
#class for all db operations using mongodb
db = dbops.MongoORM()

#instanttiate class for common validations
valids = validations.Validations()

rclient = StrictRedis()

NUM_RECORDS_TO_FETCH=50

VERIFICATION_LIMIT = 3

taskssize = 10

def fetchUsersRecords():
    records = list()
    v_res = db.getUsersToBeVerifiedRecords()
    v_recs = [ i for i in v_res if(i['verify_count'] <= VERIFICATION_LIMIT)]
    logger.info("Records size fetched {}".format(len(v_recs)))

    s_res = db.getUsersToBeSuspended(verification=VERIFICATION_LIMIT)
    s_recs = []
    for i in s_res:
        if i.get('verify_count', 0):
            s_recs.append(i)

    logger.info("Records size fetched {}".format(len(s_recs)))
    return v_recs, s_recs

@asyncio.coroutine
def start_verification(task_name, work_queue):
    while not work_queue.empty():
        queue_item = yield from work_queue.get()
        logger.info ('{0} grabbed item for : {1}'.format(task_name, queue_item['actual']))
        #logger.info ('{0} grabbed item for : {1}'.format(task_name, queue_item))
        #yield from asyncio.sleep(0.5)
        #update the verify_count in db
        verifycount = queue_item.get('verify_count', 0) #default is 0
        if verifycount <= 3:
            db.incrementUsersVerifyField(queue_item['actual'], 1)
            #do some thing heres
        else:
            db.updateUsersSuspendedField(queue_item['actual'], 'True')
            #do not send out mail or send account suspended mail
            #suspend for 1 hour and then reactivate

    return True

@asyncio.coroutine
def start_suspension(task_name, work_queue):
    while not work_queue.empty():
        queue_item = yield from work_queue.get()
        logger.info ('{0} grabbed item for : {1}'.format(task_name, queue_item['actual']))
        #logger.info ('{0} grabbed item for : {1}'.format(task_name, queue_item))
        #yield from asyncio.sleep(0.5)
        #update the verify_count in db
        verifycount = queue_item.get('verify_count', 0) #default is 0
        if verifycount <= 3:
            db.incrementUsersVerifyField(queue_item['actual'], 1)
            #do some thing heres
        else:
            db.updateUsersSuspendedField(queue_item['actual'], 'True')
            #do not send out mail or send account suspended mail
            #suspend for 1 hour and then reactivate

    return True


def start_work(v_recs, s_recs):
    if not len(v_recs) and not len(s_recs):
        logger.warn("Both v and s records are none... nothing to do")
        return True
    
    verify_q = asyncio.Queue()
    suspend_q = asyncio.Queue()

    loop = asyncio.get_event_loop()

    for rec in v_recs:
        verify_q.put_nowait(rec)

    for rec in s_recs:
        suspend_q.put_nowait(rec)

    tasks = []

    if not verify_q.empty():
        j = 0
        for i in range(taskssize):
            name = 'verification_task_'+ str(j)
            tasks.append(asyncio.async(start_verification(name, verify_q)))
            j+=1

    if not suspend_q.empty():
        j = 0
        for i in range(taskssize):
            name = 'suspension_task_'+str(j)
            tasks.append(asyncio.async(start_suspension(name, suspend_q)))
            j+=1

    loop.run_until_complete(asyncio.wait(tasks))
    loop.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PhoneVerification- .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    parser.add_argument( '-d', '--debug', help='email dump file', required=False)

    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    handler='Phone_Verif_initiate-['+instance+']'
    formatter=('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
    logger = logging.getLogger('phone_verification_handler')

    debugfile = ''
    if 'debug' in argsdict and argsdict['debug'] is not None:
        debugfile = argsdict['debug']
        verify_recs = []
        suspend_recs = []
        for i in range(1,10, 1):
            verify_recs.append(i)
        for i in range(30,40, 2):
            suspend_recs.append(i)
        exit()

    verify_recs, suspend_recs = fetchUsersRecords()
    if len(verify_recs) or len(suspend_recs):
        start_work(verify_recs, suspend_recs)
    else:
        logger.error("No Records to Verify")
    #Fetch the docs from db and initiate session for the same
