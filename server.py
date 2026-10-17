"""Afterglow local prototype. Python standard library only."""
import concurrent.futures
import datetime as dt
import json
import math
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen
from pathlib import Path

ROOT = Path(__file__).parent
UTC = dt.timezone.utc

def geocode(query):
    query = query.strip()
    if not 2 <= len(query) <= 160:
        raise ValueError('请输入2至160个字符的城市、景点或地址')
    places = []
    failed = 0
    try:
        data = fetch('https://photon.komoot.io/api/?' + urlencode({'q': query, 'limit': 6}))
        for feature in data.get('features', []):
            p = feature['properties']
            lon, lat = feature['geometry']['coordinates'][:2]
            label = ' · '.join(dict.fromkeys(str(p[k]) for k in ('name','street','housenumber','city','state','country') if p.get(k)))
            places.append(dict(name=label or query, latitude=lat, longitude=lon, source='Photon / OpenStreetMap'))
    except Exception:
        failed += 1
    if not places:
        try:
            data = fetch('https://geocoding-api.open-meteo.com/v1/search?' + urlencode({'name':query,'count':6,'language':'zh','format':'json'}))
            for p in data.get('results', []):
                label = ' · '.join(dict.fromkeys(p[k] for k in ('name','admin1','country') if p.get(k)))
                places.append(dict(name=label, latitude=p['latitude'], longitude=p['longitude'], timezone=p.get('timezone'), source='Open-Meteo / GeoNames'))
        except Exception:
            failed += 1
    if failed == 2:
        raise ValueError('地址服务暂时无法连接，请重试或使用当前位置、手填坐标。')
    return dict(results=places)

def fetch(url):
    req = Request(url, headers={'User-Agent': os.environ.get('WEATHER_USER_AGENT', 'Afterglow/0.2 https://github.com/XLJFZ/afterglow')})
    with urlopen(req, timeout=25) as r:
        return json.load(r)

def solar(t, lat, lon):
    # NOAA fractional-year approximation; geometric altitude, no terrain/refraction.
    n = t.timetuple().tm_yday
    hour = t.hour + t.minute / 60 + t.second / 3600
    g = 2 * math.pi / 365 * (n - 1 + (hour - 12) / 24)
    eq = 229.18 * (.000075 + .001868*math.cos(g) - .032077*math.sin(g) - .014615*math.cos(2*g) - .040849*math.sin(2*g))
    dec = .006918-.399912*math.cos(g)+.070257*math.sin(g)-.006758*math.cos(2*g)+.000907*math.sin(2*g)-.002697*math.cos(3*g)+.00148*math.sin(3*g)
    ha = math.radians(((hour*60+eq+4*lon) % 1440)/4-180)
    p = math.radians(lat)
    alt = math.degrees(math.asin(math.sin(p)*math.sin(dec)+math.cos(p)*math.cos(dec)*math.cos(ha)))
    az = (math.degrees(math.atan2(math.sin(ha), math.cos(ha)*math.sin(p)-math.tan(dec)*math.cos(p)))+180)%360
    return alt, az

def astronomy(day, lat, lon, offset):
    tz = dt.timezone(dt.timedelta(hours=offset))
    start = dt.datetime.combine(day, dt.time(), tzinfo=tz).astimezone(UTC)
    events = {}
    previous = solar(start, lat, lon)[0]
    for minute in range(1, 1441):
        t = start + dt.timedelta(minutes=minute)
        alt, az = solar(t, lat, lon)
        for name, threshold in [('golden_start',6),('sunset',-.833),('blue_start',-4),('blue_end',-6)]:
            if previous > threshold >= alt:
                fraction = (previous-threshold)/(previous-alt)
                event = t-dt.timedelta(minutes=1-fraction)
                events[name] = event.astimezone(tz).isoformat()
                if name == 'sunset': events['azimuth'] = round(solar(event,lat,lon)[1],1)
        previous = alt
    return events

def destination(lat, lon, bearing, km):
    p,l,b = map(math.radians,(lat,lon,bearing))
    d=km/6371
    p2=math.asin(math.sin(p)*math.cos(d)+math.cos(p)*math.sin(d)*math.cos(b))
    l2=l+math.atan2(math.sin(b)*math.sin(d)*math.cos(p), math.cos(d)-math.sin(p)*math.sin(p2))
    return round(math.degrees(p2),5), round((math.degrees(l2)+180)%360-180,5)

FIELDS = ['cloud_cover_low','cloud_cover_mid','cloud_cover_high','relative_humidity_2m','visibility','precipitation','wind_speed_10m']
def openmeteo(lat,lon,day,model):
    q = urlencode(dict(latitude=lat,longitude=lon,hourly=','.join(FIELDS),start_date=day,end_date=day,timezone='UTC',models=model))
    data=fetch('https://api.open-meteo.com/v1/forecast?'+q)['hourly']
    return [dict(time=t+'+00:00', **{f:data[f][i] for f in FIELDS}) for i,t in enumerate(data['time'])]

def metno(lat,lon,day,model=None):
    data=fetch('https://api.met.no/weatherapi/locationforecast/2.0/complete?'+urlencode(dict(lat=lat,lon=lon)))
    rows=[]
    for x in data['properties']['timeseries']:
        v=x['data']['instant']['details']
        rows.append(dict(time=x['time'].replace('Z','+00:00'), cloud_cover_low=v.get('cloud_area_fraction_low'),cloud_cover_mid=v.get('cloud_area_fraction_medium'),cloud_cover_high=v.get('cloud_area_fraction_high'),relative_humidity_2m=v.get('relative_humidity'),visibility=None,precipitation=x['data'].get('next_1_hours',{}).get('details',{}).get('precipitation_amount'),wind_speed_10m=v.get('wind_speed',0)*3.6))
    return rows

PROVIDERS={'openmeteo':openmeteo,'metno':metno}
def nearest(rows,t):
    if not rows: raise ValueError('没有可用时次')
    row=min(rows,key=lambda x:abs((dt.datetime.fromisoformat(x['time'])-t).total_seconds()))
    if abs((dt.datetime.fromisoformat(row['time'])-t).total_seconds())>5400: raise ValueError('日期不在该平台可用预报范围内')
    return row

def score(row, samples, trend):
    low,mid,high=[row.get(f) for f in FIELDS[:3]]
    if any(v is None for v in (low,mid,high)): raise ValueError('缺少分层云量，无法评分')
    light=max(0,100-abs((high*.6+mid*.4)-50)*2)
    obstruction=100-max(s['cloud_cover_low'] for s in samples)
    texture=max(0,100-abs(high-mid)*.6)
    visibility=row.get('visibility')
    transparent=min(100,visibility/200) if visibility is not None else None
    evolution=max(0,100-abs(trend)*2) if trend is not None else None
    dimensions=[('中高云受光潜力',light,.35),('日落方向通透度',obstruction,.25),('云层结构代理指标',texture,.20),('大气透明度',transparent,.10),('窗口内云量稳定性',evolution,.10)]
    available=[x for x in dimensions if x[1] is not None]
    value=sum(v*w for _,v,w in available)/sum(w for _,v,w in available)
    rain=row.get('precipitation')
    if rain is not None: value *= max(.25,1-min(rain,3)*.2)
    return round(value),[dict(name=n,value=None if v is None else round(v),weight=round(w*100)) for n,v,w in dimensions]

def forecast(lat,lon,day,offset,provider,model,bearing):
    astro=astronomy(day,lat,lon,offset)
    if 'sunset' not in astro: return dict(astronomy=astro,unavailable='该日期在当地没有日落事件，无法计算晚霞指数。')
    sunset=dt.datetime.fromisoformat(astro['sunset'])
    get=PROVIDERS[provider]
    points=[(lat,lon,0,astro['azimuth'])]+[(*destination(lat,lon,astro['azimuth']+a,d),d,astro['azimuth']+a) for d in (30,80) for a in (-30,0,30)]
    def task(p):
        try:
            rows=get(p[0],p[1],sunset.astimezone(UTC).date().isoformat(),model)
            return dict(lat=p[0],lon=p[1],distance=p[2],bearing=p[3],row=nearest(rows,sunset),rows=rows)
        except Exception as e: return dict(distance=p[2],error=str(e))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(task,points))
    center=results[0]
    if 'error' in center: raise ValueError('数据源请求失败：'+center['error'])
    valid=[r for r in results[1:] if 'row' in r and r['row'].get('cloud_cover_low') is not None]
    if not valid: raise ValueError('日落方向采样失败，暂不输出空间评分；请重试或切换平台。')
    r=center['row']; timeline=[]
    for x in center['rows']:
        t=dt.datetime.fromisoformat(x['time'])
        if abs((t-sunset).total_seconds())<3*3600:
            timeline.append(dict(x,local_time=t.astimezone(sunset.tzinfo).strftime('%H:%M')))
    clouds=[x['cloud_cover_mid'] for x in timeline if x.get('cloud_cover_mid') is not None]
    trend=max(clouds)-min(clouds) if len(clouds)>1 else None
    value,dimensions=score(r,[s['row'] for s in valid],trend)
    angle=None if bearing is None else abs((bearing-astro['azimuth']+180)%360-180)
    complete=sum(r.get(f) is not None for f in FIELDS)/len(FIELDS)
    lead=max(0,(sunset-dt.datetime.now(UTC)).total_seconds()/86400)
    reliability='中' if complete==1 and len(valid)==6 and lead<2 else '低'
    return dict(astronomy=astro,score=value,dimensions=dimensions,weather=r,timeline=timeline,samples=[{k:v for k,v in s.items() if k!='rows'} for s in results],provider=provider,model=model if provider=='openmeteo' else 'MET Locationforecast',confidence=reliability,confidence_note='依据数据完整性、采样成功数与预报时效；未进行跨模型一致性验证，不是统计置信区间。',alignment=None if angle is None else round(angle),window=[(sunset-dt.timedelta(minutes=30)).isoformat(),(sunset+dt.timedelta(minutes=20)).isoformat()],fetched_at=dt.datetime.now(UTC).isoformat(),version='rules-0.1',warnings=['拍摄窗口为日落前30分钟至后20分钟的初始经验窗口，尚非天气优化结果。','未接入地形、建筑遮挡和云光学厚度；空间云量不能直接代表光路遮挡。','指数与色彩强度、晚霞发生概率均未做历史校准。']+(['存在缺失字段或空间采样失败，可靠性降低。'] if complete<1 or len(valid)<6 else []))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT/'web'),**kw)
    def do_GET(self):
        parsed=urlparse(self.path)
        if parsed.path == '/api/v1/metno':
            try:
                q = parse_qs(parsed.query)
                lat, lon = float(q['lat'][0]), float(q['lon'][0])
                if not (math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
                    raise ValueError('无效坐标')
                result = fetch('https://api.met.no/weatherapi/locationforecast/2.0/complete?' + urlencode({'lat':f'{lat:.4f}','lon':f'{lon:.4f}'}))
                status = 200
            except Exception:
                result, status = {'error':'MET Norway 暂不可用'}, 502
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'private, max-age=600')
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/api/v1/geocode':
            try:
                result = geocode(parse_qs(parsed.query).get('q', [''])[0])
                status = 200
            except ValueError as e:
                result, status = {'error': str(e)}, 400
            body = json.dumps(result, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path not in ('/api/v1/forecast', '/api/v1/sunset'): return super().do_GET()
        try:
            q={k:v[0] for k,v in parse_qs(parsed.query).items()}
            lat,lon=float(q.get('lat',24.48)),float(q.get('lon',118.08))
            offset=float(q.get('offset',8)); raw_bearing=q.get('bearing'); bearing=None if raw_bearing in (None,'','unknown') else float(raw_bearing)
            if not all(math.isfinite(x) for x in (lat,lon,offset)) or not(-90<=lat<=90 and -180<=lon<=180 and -12<=offset<=14 and (bearing is None or (math.isfinite(bearing) and 0<=bearing<=360))): raise ValueError('坐标、时区或朝向超出范围')
            day=dt.date.fromisoformat(q.get('date',dt.datetime.now(UTC).date().isoformat()))
            provider=q.get('provider','openmeteo'); model=q.get('model','best_match')
            if provider not in PROVIDERS or model not in ('best_match','gfs_seamless','icon_seamless'): raise ValueError('不支持的数据源或模型')
            result = (dict(astronomy=astronomy(day,lat,lon,offset)) if parsed.path == '/api/v1/sunset'
                      else forecast(lat,lon,day,offset,provider,model,bearing))
            status=200
        except ValueError as e: result={'error':str(e)}; status=400
        except Exception: result={'error':'天气服务暂不可用，请稍后重试。'}; status=502
        body=json.dumps(result,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)

if __name__=='__main__':
    print('Afterglow: http://127.0.0.1:8765',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()

