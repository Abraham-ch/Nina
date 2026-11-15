import json
import os
import re
import httpx
from .analytics import get_analysis

def respond(analysis, question, role='gestion'):
    q=question.lower();s=analysis['selected'];sel=analysis['selection']
    guidance={'gestion':'For territorial monitoring, compare the same month and check whether the archive is partial before prioritizing a review.',
              'ciencia':'To evaluate the result, review the provenance, the instrumental reference and the train/test split.',
              'comunicacion':'When communicating the result, include territory, period and source, and keep the term detections to describe the archive pixels.'}.get(role,'Review the evidence and the provenance of the analysis.')
    role={'gestion':'territorial management','ciencia':'research','comunicacion':'public communication'}.get(role,'territorial management')
    evidence=[{'id':'E1','label':'Selected analysis','value':f"{analysis['area_name']} · {sel['selected_year']}-{sel['selected_month']:02d}"},
              {'id':'E2','label':'Detections / estimate','value':s['value']},
              {'id':'E3','label':'Median of the same month','value':s['historical_median']},
              {'id':'E4','label':'Eligible years','value':s['historical_n']},
              {'id':'E5','label':'Valid coverage','value':'Not reconstructed: requires L2 masks and observation opportunities'}]
    engine='deterministic_evidence'; framing=None
    if any(w in q for w in ['mañana','predic','evacua','brigada','provocado','causa del','tomorrow','forecast','brigade','arson','cause of']):
        text='Historical detections cannot confirm causes, predict spread or prescribe an emergency response. This analysis describes the observed archive.'
    elif any(w in q for w in ['sensor','satél','satel','viirs','modis','armoniz','harmoni']):
        text='MODIS and VIIRS differ in resolution, sensitivity and overpass times. Their raw counts must stay separate. The lab offers an exploratory calibration; the harmonized product has its own evaluation and publication gates. Local L2 observation opportunities are not reconstructed yet.'
    elif any(w in q for w in ['cobertura','nube','calidad','confian','fiab','suficien','coverage','cloud','quality','reliab','sufficient']):
        text='The denominator of valid observation opportunities is not available yet for this selection. The calendar can describe archive detections, but cannot tell whether an absence comes from clouds, a missing overpass or no signal.'
    elif s['value'] is None:
        text='The selection has no output available for this metric. Check the platform, the period or the model conditions. NINA keeps the value as unavailable.'
    else:
        text=f"The archive for {analysis['area_name']} holds {s['value']:,.0f} {'detections' if sel['metric']=='observed' else 'exploratory equivalent pixels'} for {sel['selected_year']}-{sel['selected_month']:02d}. "
        if s['historical_median'] is not None:
            text+=f"The median of the same month over the {s['historical_n']} previous eligible years is {s['historical_median']:,.1f}. "
            if s['anomaly_percent'] is not None: text+=f"The descriptive difference is {s['anomaly_percent']:+.1f}%. "
        else: text+='There are not at least five eligible years for a historical median. '
        if s['status']=='partial_archive': text+='The period is partial or its monthly completeness is unknown; the anomaly is omitted. '
        text+='The comparison is not corrected for observation coverage and does not measure individual fires.'
    base=os.getenv('NINA_LLM_BASE_URL');key=os.getenv('NINA_LLM_API_KEY');model=os.getenv('NINA_LLM_MODEL')
    if base and key and model:
        # Numerical facts are always rendered by the deterministic engine. The LLM
        # contributes a short role-specific reading cue, forbidden to introduce figures.
        try:
            response=httpx.post(base.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},timeout=25,
                json={'model':model,'messages':[{'role':'system','content':'Write one sentence in English to guide the reading of this analysis for the role. You may only recommend reviewing evidence, coverage or provenance. No figures, causes, forecasts or operational instructions. Return JSON with the key framing.'},
                    {'role':'user','content':json.dumps({'role':role,'verified_text':text,'question':question},ensure_ascii=False)}],
                    'response_format':{'type':'json_object'}})
            response.raise_for_status();candidate=json.loads(response.json()['choices'][0]['message']['content'])['framing']
            if isinstance(candidate,str) and 5<len(candidate)<250 and not re.search(r'\d|evac|brigad|incendio provoc|pron[oó]st|arson|forecast',candidate,re.I):
                framing=candidate;engine='llm_with_verified_facts'
        except Exception: pass
    return {'analysis_id':analysis['id'],'engine':engine,'role':role,'answer':text,'framing':framing,'guidance':guidance,
            'evidence':evidence,'references':analysis['references'],'synthetic':False}
