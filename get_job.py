import urllib.request
import re
try:
    html = urllib.request.urlopen("https://news.ycombinator.com/jobs").read().decode('utf-8')
    match = re.search(r'href="(https://boards\.greenhouse\.io/[^"]+)"', html)
    if match:
        print(match.group(1))
    else:
        print("https://jobs.lever.co/supabase/1df3f706-9b62-44df-9e2e-2e0616b7720c")
except:
    print("https://jobs.lever.co/supabase/1df3f706-9b62-44df-9e2e-2e0616b7720c")
