import {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import App from './App';
import Landing from './landing/Landing';
import './style.css';

// Portada salvo enlaces compartidos (?s=) o #atlas; el botón "Atrás" vuelve a la portada.
const inAtlas = () => location.hash === '#atlas' || new URLSearchParams(location.search).has('s');

function Root() {
  const [atlas, setAtlas] = useState(inAtlas);
  useEffect(() => {
    const sync = () => setAtlas(inAtlas());
    addEventListener('hashchange', sync);
    return () => removeEventListener('hashchange', sync);
  }, []);
  useEffect(() => { scrollTo(0, 0); }, [atlas]);
  return atlas ? <App/> : <Landing onEnter={() => { location.hash = 'atlas'; }}/>;
}

createRoot(document.getElementById('root')!).render(<Root/>);
