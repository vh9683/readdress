import pymongo

conn = pymongo.MongoClient()
db = conn.testdb.test

db.insert( {'email':'test'})
db.insert( {'email1':'test1'})

for i in range(10):
    op = { '$addToSet' : { 'references' : i }}
    db.update( { 'email' : 'test' }, op , False, False )

    op = { '$addToSet' : { 'references1' : i }}
    db.update( { 'email1' : 'test1' }, op , False, False )

for i in range(10):
    result = db.find( { 'email':'test', 'references': {'$in' : [i]}} )
    for item in result:
        print (item)

#db.update( { '$pull' : {'references': { '$in' : [2,4]} }} , {'email':'test'}  )
print (db.update( {'email':'test'}, {'$pull' : {'references': { '$in' : [2,4]}}}))

