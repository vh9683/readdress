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
    item = pickle.loads(item)
    print('item ' + str(item))
    db.insert( item[0] )
    print ('len of mailarchivebackup is : {}'.format(r.llen('mailarchivebackup')))
    r.lrem('mailarchivebackup', 0, item)
    print ('len of mailarchivebackup is : {}'.format(r.llen('mailarchivebackup')))

