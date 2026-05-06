import urllib.request
import re
import json

req = urllib.request.Request(
    'https://jobs.netflix.com/api/search',
    headers={'User-Agent': 'Mozilla/5.0'}
)
try:
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode('utf-8'))
    for job in data.get('records', {}).get('postings', []):
        if 'engineer' in job.get('text', '').lower():
            print(f"https://jobs.netflix.com/jobs/{job.get('external_id')}")
            break
except Exception as e:
    print("Failed", e)
