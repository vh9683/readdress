#! /usr/bin/python3.4


import sys
from redis import StrictRedis
from bson import Binary
import pymongo
import pickle

if __name__ == '__main__':
  instance = sys.argv[-1]

  if not instance:
    instance = "1"

  try:
    conn=pymongo.MongoClient()
    print ("Connected successfully!!!")
  except pymongo.errors.ConnectionFailure as e:
    print ("Could not connect to MongoDB: %s" % e )

  db = conn.inbounddb.mailBackup
  r = StrictRedis()

  while True:
    item = r.brpoplpush('mailarchive', 'mailarchivebackup')
    message = pickle.loads(item)
    db.insert( {'from':message['msg']['from_email'], 'inboundJson':Binary(str(message).encode(), 128)} )
    print ('len of mailarchivebackup is : {}'.format(r.llen('mailarchivebackup')))
    r.lrem('mailarchivebackup', 0, item)
    print ('len of mailarchivebackup is : {}'.format(r.llen('mailarchivebackup')))

