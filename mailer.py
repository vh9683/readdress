import mandrill
import redis
import pickle
mclient = mandrill.Mandrill('c3JOgoZZ9BmKN4swnnBEpQ')
rclient = redis.StrictRedis()

ps = rclient.pubsub()
ps.subscribe(['mailer'])

for item in ps.listen():
  if item['type'] == 'message':
    data = pickle.loads(item['data'])
    print('mailer request ' + str(data))
    res = mclient.messages.send_template(template_name=data['template_name'],template_content=[],message={'to': [{'email': data['email']}], 'merge_language': 'handlebars', 'global_merge_vars': data['global_merge_vars']})
    print('send result ' + str(res))
