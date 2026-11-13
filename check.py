import os,sys,json,copy,io,hashlib
from uuid import uuid4
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['DATA_DIR']=str(ROOT/'data');os.environ['DATABASE_PATH']=str(ROOT/'data/jobs.db')
for key in ['GEMINI_API_KEY','VLM_API_KEY','OPENROUTER_API_KEY']:os.environ.pop(key,None)
sys.path.insert(0,str(ROOT/'source'))
from fastapi.testclient import TestClient
from src.reconciliation.models import DocumentExtraction
from src.reconciliation.engine import reconcile_documents
import src.main as main
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import pypdfium2 as pdfium
from PIL import Image,ImageChops
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))

def deny(*a,**kw):raise RuntimeError('Live provider/parsing disabled for this offline validation')
main.parse_document=deny;main.GeminiDocumentExtractor=deny

def base(kind):
 return dict(document_id=kind,document_type=kind,document_number='DEMO-'+kind,vendor_name='Demo Vendor',currency='USD',line_items=[dict(sku='SKU-A',description='Widget',quantity=10,unit_price=10,total_price=100)],subtotal=100,total_amount=100)

def docs(i,p):
 return DocumentExtraction.model_validate(i),DocumentExtraction.model_validate(p)

cases=[]
for name,expected in [('clean',set()),('unit_price',{'unit_price_mismatch','line_total_mismatch'}),('quantity',{'quantity_mismatch','line_total_mismatch'}),('currency',{'currency_mismatch'}),('missing',{'missing_item'}),('arithmetic',{'arithmetic_error','line_total_mismatch'}),('chinese_vendor',{'vendor_mismatch'}),('fractional_quantity',set())]:
 i,p=base('invoice'),base('purchase_order')
 if name=='unit_price':i['line_items'][0].update(unit_price=12,total_price=120);i.update(subtotal=120,total_amount=120)
 if name=='quantity':i['line_items'][0].update(quantity=12,total_price=120);i.update(subtotal=120,total_amount=120)
 if name=='currency':i['currency']='EUR'
 if name=='missing':i['line_items']=[];i.update(subtotal=0,total_amount=0)
 if name=='arithmetic':i['line_items'][0]['total_price']=90;i.update(subtotal=90,total_amount=90)
 if name=='chinese_vendor':i['vendor_name']='甲方公司';p['vendor_name']='乙方公司'
 if name=='fractional_quantity':
  for d in (i,p):d['line_items'][0].update(quantity=.125,unit_price=8,total_price=1);d.update(subtotal=1,total_amount=1)
 folder=ROOT/'cases'/name;folder.mkdir(parents=True)
 for d in (i,p):
  path=folder/(d['document_type']+'.pdf');c=canvas.Canvas(str(path),pagesize=(612,792),invariant=1)
  c.setFont('Helvetica',14);c.drawString(45,750,'FICTIONAL - PRETYPED EXTRACTION TEST')
  lines=[('vendor_name','Vendor: '+d['vendor_name']),('currency','Currency: '+d['currency'])]
  lines += [('row',f"{x['sku']} {x['description']} Qty {x['quantity']} Price {x['unit_price']} Total {x['total_price']}") for x in d['line_items']]
  for n,(field,text) in enumerate(lines):
   c.setFont('STSong-Light' if field=='vendor_name' and name=='chinese_vendor' else 'Helvetica',11);c.drawString(45,700-n*30,text)
  c.save();pdf=pdfium.PdfDocument(path);page=pdf[0];tp=page.get_textpage();d['field_evidence']={}
  for field,text in lines:
   search=tp.search(text,match_case=True);match=search.get_next();assert match,(name,text)
   count=tp.count_rects(*match);rs=[tp.get_rect(j) for j in range(count)];left=min(r[0] for r in rs);bottom=min(r[1] for r in rs);right=max(r[2] for r in rs);top=max(r[3] for r in rs)
   ev=dict(document_id=d['document_id'],page=1,text=text,bbox=[left/612,1-top/792,right/612,1-bottom/792],confidence=1)
   if field=='row':d['line_items'][0]['evidence']=ev
   else:d['field_evidence'][field]=ev
   search.close()
  tp.close();page.close();pdf.close()
 inv,po=docs(i,p);result=reconcile_documents(inv,po).model_dump(mode='json');pred={x['type'] for x in result['discrepancies']}
 job='local-'+name+'-'+uuid4().hex[:8];main.store.create(job,str(folder/'invoice.pdf'),str(folder/'purchase_order.pdf'));main.store.update(job,status='completed',result=result)
 (folder/'input.json').write_text(json.dumps({'invoice':i,'purchase_order':p},ensure_ascii=False,indent=2))
 (folder/'initial.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 cases.append(dict(case=name,expected=sorted(expected),actual=sorted(pred),passed=pred==expected,job_id=job))
client=TestClient(main.app)
review=[]
for case in cases[:6]:
 current=client.get('/api/v1/jobs/'+case['job_id']).json()['result']; corrected=copy.deepcopy(current['purchase_order']);corrected['document_type']='invoice';corrected['document_id']='invoice';corrected['document_number']=current['invoice']['document_number']
 r=client.put('/api/v1/jobs/'+case['job_id']+'/review',json={'invoice':corrected,'note':'Synthetic edit to exercise recalculation, not a verified correction'})
 assert r.status_code==200,r.text
 payload=r.json();assert payload['summary']['discrepancy_count']==0
 assert payload['reviewer_edits'][0]['before']['invoice']==current['invoice']
 assert client.get('/api/v1/jobs/'+case['job_id']+'/export').json()==payload
 review.append({'case':case['case'],'after_discrepancy_count':0,'audit_and_export_passed':True})
# Upstream prerecorded PDFs: genuine source-location and PNG highlight endpoint checks.
sample=client.post('/api/v1/sample').json();job=sample['job_id'];result=client.get('/api/v1/jobs/'+job).json()['result'];evidence=result['discrepancies'][0]['invoice_evidence']
plain=client.get(f'/api/v1/jobs/{job}/documents/invoice/preview');highlight=client.get(f'/api/v1/jobs/{job}/documents/invoice/preview',params={'bbox':','.join(map(str,evidence['bbox']))})
assert plain.status_code==highlight.status_code==200
out=ROOT/'evidence';out.mkdir();(out/'sample-plain.png').write_bytes(plain.content);(out/'sample-highlight.png').write_bytes(highlight.content)
a=Image.open(io.BytesIO(plain.content)).convert('RGB');b=Image.open(io.BytesIO(highlight.content)).convert('RGB');assert ImageChops.difference(a,b).getbbox()
report={'source_commit':'b9b5de7bd2bbfcfd4719c895c1ee31e566f2a7f9','live_model_calls':0,'live_ocr_tested':False,'cases':cases,'case_passes':sum(x['passed'] for x in cases),'case_count':len(cases),'review_cases':review,'sample_preview':{'png_endpoints_pass':True,'highlight_changes_pixels':True,'source_bbox':evidence['bbox'],'initial_findings':len(result['discrepancies'])},'limits':['Preset extraction, no model/Docling evaluation','Review edits are synthetic changes, not verified factual corrections','No real customer documents or production security acceptance']}
(ROOT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
