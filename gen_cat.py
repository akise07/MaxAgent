import os, json, urllib.request, ssl, base64, pathlib, sys
base = os.environ.get('GPT_IMAGE_BASE_URL','').rstrip('/')
key = os.environ.get('GPT_IMAGE_API_KEY','')
if not base or not key:
    print('ERROR: missing credentials', file=sys.stderr); sys.exit(1)
api = base + '/images/generations'
payload = json.dumps({
    'model':'gpt-image-2',
    'prompt':'a cute cartoon cat, flat vector illustration style, bright colors, simple shapes, white background',
    'size':'1024x1024',
    'n':1
}).encode()
req = urllib.request.Request(api, data=payload, headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
ctx = ssl.create_default_context()
try:
    with urllib.request.urlopen(req, context=ctx, timeout=180) as r:
        body = json.loads(r.read().decode('utf-8','ignore'))
except Exception as e:
    print('API request failed:', e, file=sys.stderr); sys.exit(1)
if 'data' not in body or not body['data']:
    print('No data in response:', body, file=sys.stderr); sys.exit(1)
item = body['data'][0]
if 'b64_json' in item:
    out = pathlib.Path('gpt_image_2.png')
    out.write_bytes(base64.b64decode(item['b64_json']))
    print('SUCCESS:'+str(out))
elif 'url' in item:
    print('URL:'+item['url'])
else:
    print('Unknown response format:', item, file=sys.stderr); sys.exit(1)
