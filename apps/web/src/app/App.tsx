import { firms } from "@fire/schemas";

export function App() {
    return (
        <>
            <main>
                <h1>Calendario de actividad de incendios</h1>
                <p role="note">{firms.es.warning}</p>
            </main>
            {/* Pie obligatorio (AGENTS.md §11) */}
            <footer>
                <p>{firms.es.citation}</p>
                <a href={firms.url}>{firms.es.disclaimer_label}</a>
            </footer>
        </>
    );
}
