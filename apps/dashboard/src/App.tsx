const cards = [
  {
    title: "Overview",
    body: "Estimated savings, current mode, and recent compaction events will land here."
  },
  {
    title: "Reducers",
    body: "Reducer firing frequency, risk posture, and before/after examples."
  },
  {
    title: "Benchmarks",
    body: "Reduction versus preservation tradeoffs with explicit pass/fail gates."
  }
];

export default function App() {
  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">Context OS</p>
        <h1>Local context reduction with explicit tradeoffs.</h1>
        <p className="lede">
          The dashboard is scaffolded in this checkpoint and will be wired to
          SQLite telemetry as the proxy and benchmark pipeline land.
        </p>
      </header>
      <section className="grid">
        {cards.map((card) => (
          <article key={card.title} className="card">
            <h2>{card.title}</h2>
            <p>{card.body}</p>
          </article>
        ))}
      </section>
    </main>
  );
}
