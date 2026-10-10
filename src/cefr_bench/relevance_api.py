"""API relevance client; never invoked by local answer acquisition."""
import json
import requests
from .relevance import CRITERION, relevance_prompt, parse_relevance_json, relevance_probes

SCHEMA = {
    'type':'object','additionalProperties':False,'required':['results'],
    'properties':{'results':{'type':'array','minItems':1,'maxItems':1,'items':{
        'type':'object','additionalProperties':False,
        'required':['criterion','passed','reason','confidence'],
        'properties':{'criterion':{'type':'string','enum':[CRITERION]},
                      'passed':{'type':'boolean'},'reason':{'type':'string'},
                      'confidence':{'type':'integer','minimum':0,'maximum':100}}
    }}}
}


class RelevanceClient:
    def __init__(self,key,model,provider=None):
        self.key,self.model,self.provider = key,model,provider
        self.reports = []

    def assess(self,question,reply):
        body = {'model':self.model,'messages':[{'role':'user','content':relevance_prompt(question,reply)}],
                'temperature':0,'max_tokens':512,
                'response_format':{'type':'json_schema','json_schema':{'name':'relevance','strict':True,'schema':SCHEMA}}}
        if self.provider:
            body['provider'] = {'only':[self.provider],'allow_fallbacks':False,'require_parameters':True}
        response = requests.post('https://openrouter.ai/api/v1/chat/completions',
                    headers={'Authorization':'Bearer '+self.key},json=body,timeout=120)
        if response.status_code != 200:
            raise RuntimeError(f'Relevance provider HTTP {response.status_code}; sample unscored')
        payload = response.json()
        choice = payload['choices'][0]
        if choice.get('finish_reason') == 'length':
            raise ValueError('Truncated judge report; sample unscored')
        report = json.loads(choice['message']['content'])
        passed = parse_relevance_json(report)
        self.reports.append({'model':self.model,'provider':payload.get('provider'),
                             'request_id':payload.get('id'),'usage':payload.get('usage'),
                             'assessment':report})
        return passed

    def validate(self):
        probes = relevance_probes()
        for expected,question,reply in probes:
            if self.assess(question,reply) is not expected:
                raise RuntimeError('Relevance preflight disagreed; do not start evaluation')
        return {'agreement':len(probes),'total':len(probes),'reports':self.reports[:len(probes)]}
