"""Fake Gemini SDK contract: no credentials and no network requests."""
import json
import sys
from types import ModuleType, SimpleNamespace
from app.gemini import classify

class FakeModel:
    def __init__(self,data):self.data=data;self.calls=[]
    def generate_content(self,**kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.data),
             usage_metadata=SimpleNamespace(prompt_token_count=135,candidates_token_count=42))

def mock_google(monkeypatch,model):
    pkg=ModuleType('google')
    sdk=ModuleType('google.genai')
    modtypes=ModuleType('google.genai.types')
    modtypes.GenerateContentConfig=lambda **kwargs:SimpleNamespace(**kwargs)
    sdk.Client=lambda **kwargs:SimpleNamespace(models=model)
    sdk.types=modtypes
    pkg.genai=sdk
    for name,module in [('google',pkg),('google.genai',sdk),('google.genai.types',modtypes)]:
        monkeypatch.setitem(sys.modules,name,module)

CRITERIA=[{'key':'wheels_22','description':'22-inch wielen gemonteerd','synonyms':['22 inch',"22'' velgen"]}]

def test_gemini_schema_and_usage(monkeypatch):
    model=FakeModel({'results':[{'criterion_key':'wheels_22','status':'PRESENT','confidence':.99,
                                'evidence_quote':"22'' wielen",'reason_short':'Maat en wielcontext expliciet'}]})
    mock_google(monkeypatch,model)
    result,log=classify("XC90 met 22'' wielen",CRITERIA)
    assert result[0]['status']=='PRESENT'
    assert log['tokens_in']==135 and log['tokens_out']==42
    assert '22' in model.calls[0]['contents']
    assert model.calls[0]['config'].response_mime_type=='application/json'

def test_hallucinated_evidence_downgraded_to_unknown(monkeypatch):
    model=FakeModel({'results':[{'criterion_key':'wheels_22','status':'PRESENT','confidence':.99,
                                'evidence_quote':'22-inch velgen','reason_short':'Ik neem het aan'}]})
    mock_google(monkeypatch,model)
    result,_=classify('XC90 met 19-inch wielen',CRITERIA)
    assert result[0]['status']=='UNKNOWN'
    assert result[0]['evidence_quote'] is None
