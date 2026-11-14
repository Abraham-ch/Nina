import json
import os
import re
import httpx
from .analytics import get_analysis

def respond(analysis, question, role='gestion'):
    q=question.lower();s=analysis['selected'];sel=analysis['selection']
    guidance={'gestion':'Para el seguimiento territorial, compara el mismo mes y comprueba si el archivo es parcial antes de priorizar una revisión.',
              'ciencia':'Para evaluar el resultado, revisa la procedencia, la referencia instrumental y la separación de entrenamiento y prueba.',
              'comunicacion':'Al comunicar el resultado, incluye territorio, período y fuente, y conserva el término detecciones para describir los píxeles del archivo.'}.get(role,'Revisa la evidencia y la procedencia del análisis.')
    role={'gestion':'gestión territorial','ciencia':'investigación','comunicacion':'comunicación pública'}.get(role,'gestión territorial')
    evidence=[{'id':'E1','label':'Análisis seleccionado','value':f"{analysis['area_name']} · {sel['selected_year']}-{sel['selected_month']:02d}"},
              {'id':'E2','label':'Detecciones / estimación','value':s['value']},
              {'id':'E3','label':'Mediana del mismo mes','value':s['historical_median']},
              {'id':'E4','label':'Años elegibles','value':s['historical_n']},
              {'id':'E5','label':'Cobertura válida','value':'No reconstruida: requiere máscaras y oportunidades L2'}]
    engine='deterministic_evidence'; framing=None
    if any(w in q for w in ['mañana','predic','evacua','brigada','provocado','causa del']):
        text='Las detecciones históricas no permiten confirmar causas ni predecir propagación o prescribir una respuesta de emergencia. Este análisis describe el archivo observado.'
    elif any(w in q for w in ['sensor','satél','satel','viirs','modis','armoniz']):
        text='MODIS y VIIRS tienen resolución, sensibilidad y pasadas diferentes. Sus conteos brutos deben mantenerse separados. El laboratorio ofrece una calibración exploratoria; la armonización con control de observación está pendiente de máscaras L2.'
    elif any(w in q for w in ['cobertura','nube','calidad','confian','fiab','suficien']):
        text='No se dispone todavía del denominador de oportunidades válidas para esta selección. El calendario puede describir detecciones del archivo, pero no determinar si una ausencia se debe a cielo nublado, falta de pasada o ausencia de señal.'
    elif s['value'] is None:
        text='La selección no tiene una salida disponible para esta métrica. Revisa la plataforma, el período o las condiciones del modelo. NINA mantiene el dato como no disponible.'
    else:
        text=f"El archivo de {analysis['area_name']} contiene {s['value']:,.0f} {'detecciones' if sel['metric']=='observed' else 'píxeles equivalentes exploratorios'} para {sel['selected_year']}-{sel['selected_month']:02d}. "
        if s['historical_median'] is not None:
            text+=f"La mediana del mismo mes en los {s['historical_n']} años elegibles anteriores es {s['historical_median']:,.1f}. "
            if s['anomaly_percent'] is not None: text+=f"La diferencia descriptiva es {s['anomaly_percent']:+.1f}%. "
        else: text+='No hay al menos cinco años elegibles para una mediana histórica. '
        if s['status']=='partial_archive': text+='El período es parcial o su integridad mensual es desconocida; se omite la anomalía. '
        text+='La comparación no está corregida por cobertura de observación y no mide incendios individuales.'
    base=os.getenv('NINA_LLM_BASE_URL');key=os.getenv('NINA_LLM_API_KEY');model=os.getenv('NINA_LLM_MODEL')
    if base and key and model:
        # Numerical facts are always rendered by the deterministic engine. The LLM
        # contributes a short role-specific reading cue, forbidden to introduce figures.
        try:
            response=httpx.post(base.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+key},timeout=25,
                json={'model':model,'messages':[{'role':'system','content':'Escribe una sola frase en español para orientar la lectura de este análisis según el rol. Solo puedes recomendar revisar evidencia, cobertura o procedencia. Sin cifras, causas, pronósticos ni instrucciones operativas. Devuelve JSON con la clave framing.'},
                    {'role':'user','content':json.dumps({'role':role,'verified_text':text,'question':question},ensure_ascii=False)}],
                    'response_format':{'type':'json_object'}})
            response.raise_for_status();candidate=json.loads(response.json()['choices'][0]['message']['content'])['framing']
            if isinstance(candidate,str) and 5<len(candidate)<250 and not re.search(r'\d|evac|brigad|incendio provoc|pron[oó]st',candidate,re.I):
                framing=candidate;engine='llm_with_verified_facts'
        except Exception: pass
    return {'analysis_id':analysis['id'],'engine':engine,'role':role,'answer':text,'framing':framing,'guidance':guidance,
            'evidence':evidence,'references':analysis['references'],'synthetic':False}
