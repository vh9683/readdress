#! /usr/bin/python3.4


import sys
from settings import r
from bson import Binary
import pymongo

if __name__ == '__main__':
  instance = sys.argv[2]

  if not instance:
    instance = "1"

  try:
    conn=pymongo.MongoClient()
    print ("Connected successfully!!!")
  except pymongo.errors.ConnectionFailure, e:
    print ("Could not connect to MongoDB: %s" % e )

  db = conn.inbounddb.mailBackup

  while True:
    item = r.brpoplpush('mailarchive', 'mailarchivebackup')
    db.insert( item[0] )
    print ('len of mailarchivebackup is : {}'.format(r.llen('mailarchivebackup')))
    r.lrem('mailarchivebackup', 0, item)
    print ('len of mailarchivebackup is : {}'.format(r.llen('mailarchivebackup')))

