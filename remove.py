from pymongo import MongoClient
import json

credentials = open('credentials.json', 'r').read()
credentials = json.loads(credentials)
conn_string = 'mongodb://%s:%s@%s:%s/%s'
credentials = conn_string % (credentials['user'],
                                         credentials['password'],
                                         credentials['host'],
                                         credentials['port'],
                                         credentials['db'])
client = MongoClient(credentials)
db = client['main']
collection = db['records']
s = set()
counter = 0
for doc in collection.find({}):
    for k in doc:
        if k != 'data' and k != 'header' and k != '_id' and k != 'href':
            s.add(k)
    counter += 1
    if counter % 10000 == 0:
        print(str(counter))

d = {value : 1 for value in s}
collection.update_many({}, {'$unset' : d})
