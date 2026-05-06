import urllib.request
import json
req = urllib.request.Request('https://remoteok.com/api', headers={'User-Agent': 'Mozilla/5.0'})
try:
    resp = urllib.request.urlopen(req).read().decode()
    data = json.loads(resp)
    for job in data[1:5]:
        if job.get('url'):
            print(job['url'])
            break
except Exception as e:
    print(e)
