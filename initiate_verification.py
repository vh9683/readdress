#! /usr/bin/python3.4

import argparse
import asyncio
import datetime
import logging
import logging.handlers
import pickle
import sys
import uuid

from redis import StrictRedis

import dbops
from config import ReConfig

readdress_configs = ReConfig()

logger = logging.getLogger('phone_verification_handler')
#class for all db operations using mongodb
db = dbops.MongoORM()

rclient = StrictRedis()

NUM_RECORDS_TO_FETCH=50

VERIFICATION_LIMIT = 3

taskssize = 10

def fetch_users_records():
    v_recs = list()
    s_recs = list()
    v_res = db.getUsersToBeVerifiedRecords()
    v_recs = [ i for i in v_res if(i.get('verify_count',0) <= VERIFICATION_LIMIT)]
    logger.info("Records size fetched {}".format(len(v_recs)))

    s_res = db.getUsersToBeSuspended(verification=VERIFICATION_LIMIT)
    s_recs = []
    for i in s_res:
        if i.get('verify_count', 0):
            s_recs.append(i)

    logger.info("Records size fetched {}".format(len(s_recs)))
    return v_recs, s_recs

def send_verification_mail(user):
    from_email = user['actual']
    mapped = user['mapped']
    phonenum = mapped.split('@')[0]
    from_name = user.get('name', '')

    session = {
        'actual'  : from_email,
        'mapped'  : mapped,
        'phonenum': phonenum,
        'name'    : from_name,
        'attempts' : 0
    }

    sessionid = uuid.uuid4().hex
    rclient.setex(sessionid, readdress_configs.get_verification_expire_time_secs() ,pickle.dumps(session))

    global_vars = {}
    validity_time = datetime.datetime.now() + datetime.timedelta(hours=readdress_configs.get_verification_expire_time_hours())

    global_vars['sessionid'] = sessionid
    global_vars['validity_time'] = validity_time

    if user.get('verify_count',0) < 3:
        msg = { 'template_name': 'verifyPhoneTemplate', 'email': from_email, 'global_merge_vars': global_vars }
    else:
        msg = { 'template_name': 'verifyPhoneTemplate_lastAttempt', 'email': from_email, 'global_merge_vars': global_vars }

    rclient.lpush('mailer',pickle.dumps(msg))
    logger.info("mailer {}".format(str(msg)) )
    return sessionid


@asyncio.coroutine
def start_verification(task_name, work_queue):
    while not work_queue.empty():
        queue_item = yield from work_queue.get()
        logger.info ('{0} grabbed item for : {1}'.format(task_name, queue_item['actual']))
        #yield from asyncio.sleep(0.5)
        #update the verify_count in db
        verifycount = queue_item.get('verify_count', 0) #default is 0
        if verifycount <= 3 and queue_item.get('suspended', 'False') == 'False':
            send_verification_mail(queue_item)
        else:
            logger.info("User :{0} verification count : {1} and suspened status :{2}".format (
            queue_item['actual'], queue_item['verify_count'], queue_item['suspended'] ))

        if 'verify_count' not in queue_item.keys():
            db.setUsersVerifyField(queue_item['actual'], 1)
        else:
            db.incrementUsersVerifyField(queue_item['actual'], 1)

    return True


def send_suspend_mail(user):
    from_email = user['actual']
    msg = { 'template_name': 'verifyPhoneTemplate', 'email': from_email }
    rclient.lpush('mailer',pickle.dumps(msg))
    logger.info("mailer {}".format(str(msg)) )
    return

@asyncio.coroutine
def start_suspension(task_name, work_queue):
    while not work_queue.empty():
        queue_item = yield from work_queue.get()
        logger.info ('{0} grabbed item for : {1}'.format(task_name, queue_item['actual']))
        queue_item['suspended'] = 'True'
        utc_timestamp = datetime.datetime.utcnow()
        queue_item['suspend_time'] = utc_timestamp
        if not db.isUserSuspended(queue_item['actual']):
           db.insertUserInSuspendedDB(queue_item)
        if db.getuser(queue_item['actual']):
           db.removeUser(queue_item)
        send_suspend_mail(queue_item)
    return True


def start_verification_suspension(v_recs, s_recs):
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

    verify_recs, suspend_recs = fetch_users_records()
    if len(verify_recs) or len(suspend_recs):
        start_verification_suspension(verify_recs, suspend_recs)
    else:
        logger.error("No Records to Verify")
    #Fetch the docs from db and initiate session for the same
