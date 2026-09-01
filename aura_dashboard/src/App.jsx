const telemetry = {
  speed: '86 km/h',
  range: '184 km',
  heading: 'N 48°',
  battery: '96%',
  latency: '1.8 ms',
  fps: '60',
  route: 'A4 → Downtown Valley',
  safetyIndex: '98.4',
};

const sensors = [
  { name: 'Front LiDAR', value: '98%', status: 'Stable', tone: 'cyan' },
  { name: 'Corner Radar', value: '92%', status: 'Tracking', tone: 'lime' },
  { name: 'Thermal Vision', value: '88%', status: 'Active', tone: 'amber' },
  { name: 'Pedestrian Depth', value: '96%', status: 'Locked', tone: 'cyan' },
];

const objects = [
  { id: 'P-142', label: 'Pedestrian', distance: '4.8 m', risk: 'Low', priority: 'Caution' },
  { id: 'V-219', label: 'Vehicle', distance: '12.1 m', risk: 'Medium', priority: 'Monitor' },
  { id: 'B-877', label: 'Barrier', distance: '2.2 m', risk: 'High', priority: 'Brake Assist' },
  { id: 'C-045', label: 'Cyclist', distance: '7.3 m', risk: 'Low', priority: 'Yield' },
];

const routeMarkers = [
  { id: 1, label: 'North Exit', x: '18%', y: '32%' },
  { id: 2, label: 'Avenue 7', x: '40%', y: '47%' },
  { id: 3, label: 'Safety Hub', x: '70%', y: '60%' },
  { id: 4, label: 'Target', x: '82%', y: '28%' },
];

const laneBars = [
  { label: 'Left', value: 24, color: 'bg-cyan-400' },
  { label: 'Center', value: 68, color: 'bg-lime-400' },
  { label: 'Right', value: 41, color: 'bg-amber-400' },
];

const zones = [
  { name: 'Pedestrian Zone', status: 'Protected', color: 'bg-lime-400' },
  { name: 'Autonomous Lane', status: 'Clear', color: 'bg-cyan-400' },
  { name: 'High Risk Sector', status: 'Watch', color: 'bg-amber-400' },
];

function Badge({ children, tone = 'cyan' }) {
  const classes = {
    cyan: 'border-cyan-400/30 bg-cyan-500/10 text-cyan-300',
    lime: 'border-lime-400/30 bg-lime-500/10 text-lime-300',
    amber: 'border-amber-400/30 bg-amber-500/10 text-amber-300',
    crimson: 'border-red-400/30 bg-red-500/10 text-red-300',
  };

  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-1 text-[10px] font-medium tracking-[0.18em] uppercase ${classes[tone]}`}>
      {children}
    </span>
  );
}

function ProgressBar({ value, tone = 'cyan' }) {
  const classes = {
    cyan: 'from-cyan-400 to-cyan-300',
    lime: 'from-lime-400 to-lime-300',
    amber: 'from-amber-400 to-amber-300',
    crimson: 'from-red-500 to-red-400',
  };

  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800/80">
      <div className={`h-full rounded-full bg-gradient-to-r ${classes[tone]}`} style={{ width: `${value}%` }} />
    </div>
  );
}

function App() {
  return (
    <div className="min-h-screen bg-abyss bg-mesh px-4 py-6 text-slate-100 md:px-6 xl:px-8">
      <div className="mx-auto max-w-[1600px]">
        <header className="mb-5 flex items-center justify-between rounded-2xl border border-borderGlow bg-panel/70 px-4 py-3 shadow-glow backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-400/30 bg-cyan-500/10 text-sm font-bold text-cyan-300">
              A
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">AuraNode AI</div>
              <div className="text-sm font-medium text-slate-100">Edge Navigation & Safety Core</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Badge tone="lime">Local AI Active</Badge>
            <Badge tone="cyan">Sensor Fusion Online</Badge>
          </div>
        </header>

        <main className="grid gap-5 xl:grid-cols-[1.7fr_1.1fr]">
          <section className="space-y-5">
            <div className="rounded-[28px] border border-borderGlow bg-panel/70 p-5 shadow-glow backdrop-blur-xl">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Driver Mode</div>
                  <h1 className="mt-1 text-2xl font-semibold text-white">Autonomous Route Intelligence</h1>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="lime">Safe Corridor</Badge>
                  <Badge tone="cyan">Live Path</Badge>
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
                <div className="rounded-[22px] border border-cyan-400/20 bg-[#0a0b10] p-3">
                  <div className="relative h-[440px] overflow-hidden rounded-[18px] border border-slate-700/80 bg-[radial-gradient(circle_at_center,_rgba(0,240,255,0.08),_transparent_40%),linear-gradient(135deg,#05070d,#0b0f16)]">
                    <div className="absolute inset-0 opacity-60" style={{
                      backgroundImage: 'linear-gradient(rgba(148,163,184,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.08) 1px, transparent 1px)',
                      backgroundSize: '32px 32px',
                    }} />

                    <div className="absolute left-5 top-4 rounded-xl border border-cyan-400/20 bg-slate-900/60 px-3 py-2 backdrop-blur-md">
                      <div className="text-[10px] uppercase tracking-[0.28em] text-slate-400">Route</div>
                      <div className="font-medium text-cyan-300">{telemetry.route}</div>
                    </div>

                    <div className="absolute right-4 top-4 flex items-center gap-2 rounded-xl border border-cyan-400/20 bg-slate-900/60 px-2 py-1.5 backdrop-blur-md">
                      <span className="h-2.5 w-2.5 rounded-full bg-lime-400 shadow-[0_0_12px_rgba(166,255,0,0.8)]" />
                      <span className="text-[11px] uppercase tracking-[0.2em] text-slate-300">Local Map</span>
                    </div>

                    <svg viewBox="0 0 800 440" className="absolute inset-0 h-full w-full">
                      <path d="M80 250 C180 180, 210 210, 300 180 S520 110, 640 170 S740 230, 760 150" fill="none" stroke="rgba(0,240,255,0.8)" strokeWidth="6" strokeLinecap="round" strokeDasharray="12 20" />
                      <path d="M90 300 L240 280 L365 220 L495 260 L668 204 L760 240" fill="none" stroke="rgba(166,255,0,0.7)" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M170 100 L260 140 L330 115 L420 150 L500 120" fill="none" stroke="rgba(255,170,0,0.4)" strokeWidth="5" strokeDasharray="10 12" />
                    </svg>

                    <div className="absolute left-[18%] top-[32%] h-4 w-4 rounded-full border border-white/60 bg-cyan-300 shadow-[0_0_24px_rgba(0,240,255,0.9)]" />
                    <div className="absolute left-[40%] top-[47%] h-4 w-4 rounded-full border border-white/60 bg-cyan-300 shadow-[0_0_24px_rgba(0,240,255,0.9)]" />
                    <div className="absolute left-[70%] top-[60%] h-4 w-4 rounded-full border border-white/60 bg-lime-300 shadow-[0_0_24px_rgba(166,255,0,0.9)]" />
                    <div className="absolute left-[82%] top-[28%] h-4 w-4 rounded-full border border-white/60 bg-amber-300 shadow-[0_0_24px_rgba(255,170,0,0.9)]" />

                    <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between gap-3">
                      <div className="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 backdrop-blur-sm">
                        <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Speed</div>
                        <div className="mt-1 text-2xl font-bold text-white">{telemetry.speed}</div>
                      </div>
                      <div className="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 backdrop-blur-sm">
                        <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Range</div>
                        <div className="mt-1 text-2xl font-bold text-white">{telemetry.range}</div>
                      </div>
                      <div className="rounded-xl border border-slate-700 bg-slate-900/70 px-3 py-2 backdrop-blur-sm">
                        <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Heading</div>
                        <div className="mt-1 text-2xl font-bold text-white">{telemetry.heading}</div>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="rounded-[22px] border border-borderGlow bg-slate-950/70 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-[10px] uppercase tracking-[0.28em] text-slate-400">System Confidence</span>
                      <span className="text-lg font-semibold text-cyan-300">{telemetry.safetyIndex}</span>
                    </div>
                    <ProgressBar value={98.4} tone="cyan" />
                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                      <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-3">
                        <div className="text-[10px] uppercase tracking-[0.24em] text-slate-400">Latency</div>
                        <div className="mt-1 text-xl font-bold text-white">{telemetry.latency}</div>
                      </div>
                      <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-3">
                        <div className="text-[10px] uppercase tracking-[0.24em] text-slate-400">FPS</div>
                        <div className="mt-1 text-xl font-bold text-white">{telemetry.fps}</div>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-[22px] border border-borderGlow bg-slate-950/70 p-4">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-[10px] uppercase tracking-[0.28em] text-slate-400">Local Sensor Stack</span>
                      <Badge tone="cyan">Fusion Locked</Badge>
                    </div>
                    <div className="space-y-3">
                      {sensors.map((sensor) => (
                        <div key={sensor.name} className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
                          <div className="mb-2 flex items-center justify-between text-sm">
                            <span className="font-medium text-slate-200">{sensor.name}</span>
                            <span className="text-slate-400">{sensor.status}</span>
                          </div>
                          <ProgressBar value={Number.parseInt(sensor.value, 10)} tone={sensor.tone} />
                          <div className="mt-2 text-right text-xs font-medium text-slate-300">{sensor.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-[28px] border border-borderGlow bg-panel/70 p-5 shadow-glow backdrop-blur-xl">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Spatial Safety</div>
                  <h2 className="mt-1 text-2xl font-semibold text-white">Adaptive Path Risk Analysis</h2>
                </div>
                <Badge tone="amber">Predictive Assist</Badge>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                {laneBars.map((lane) => (
                  <div key={lane.label} className="rounded-[20px] border border-slate-800 bg-slate-950/60 p-3">
                    <div className="mb-3 flex items-center justify-between text-sm">
                      <span className="text-slate-300">{lane.label}</span>
                      <span className="font-medium text-white">{lane.value}%</span>
                    </div>
                    <div className="mb-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-800/80">
                      <div className={`h-full rounded-full ${lane.color}`} style={{ width: `${lane.value}%` }} />
                    </div>
                    <div className="text-[10px] uppercase tracking-[0.25em] text-slate-400">
                      {lane.value > 55 ? 'High flow' : lane.value > 35 ? 'Balanced' : 'Low pressure'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <aside className="space-y-5">
            <div className="rounded-[28px] border border-borderGlow bg-panel/70 p-5 shadow-glow backdrop-blur-xl">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Pedestrian Safety</div>
                  <h2 className="mt-1 text-2xl font-semibold text-white">Local Proximity Shield</h2>
                </div>
                <Badge tone="lime">Protected</Badge>
              </div>

              <div className="rounded-[22px] border border-lime-400/20 bg-[#09110d] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-[0.28em] text-slate-400">Safety Envelope</span>
                  <span className="text-xl font-bold text-lime-300">94.9</span>
                </div>
                <div className="relative h-52 overflow-hidden rounded-[18px] border border-slate-700 bg-[radial-gradient(circle,_rgba(166,255,0,0.15),_rgba(6,16,10,0.6)_58%,_rgba(6,9,14,0.95))]">
                  <div className="absolute inset-0 animate-pulse-scan opacity-70" style={{
                    background: 'linear-gradient(180deg, transparent 0%, rgba(166,255,0,0.18) 45%, transparent 100%)',
                  }} />
                  <div className="absolute left-1/2 top-1/2 h-36 w-36 -translate-x-1/2 -translate-y-1/2 rounded-full border border-lime-400/35 bg-lime-500/10" />
                  <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-400/35 bg-cyan-500/10" />
                  <div className="absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/35 bg-white/10" />
                  <div className="absolute right-[20%] top-[34%] h-3.5 w-3.5 rounded-full bg-amber-400 shadow-[0_0_18px_rgba(255,170,0,0.9)]" />
                  <div className="absolute left-[28%] top-[52%] h-3.5 w-3.5 rounded-full bg-cyan-400 shadow-[0_0_18px_rgba(0,240,255,0.9)]" />
                  <div className="absolute left-[58%] top-[38%] h-3.5 w-3.5 rounded-full bg-lime-400 shadow-[0_0_18px_rgba(166,255,0,0.9)]" />
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {zones.map((zone) => (
                  <div key={zone.name} className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${zone.color}`} />
                      <span className="text-sm text-slate-200">{zone.name}</span>
                    </div>
                    <Badge tone={zone.name.includes('Risk') ? 'amber' : 'lime'}>{zone.status}</Badge>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-[28px] border border-borderGlow bg-panel/70 p-5 shadow-glow backdrop-blur-xl">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-[0.32em] text-slate-400">Object Tracking</div>
                  <h2 className="mt-1 text-2xl font-semibold text-white">Proximity Feed</h2>
                </div>
                <Badge tone="crimson">Alert Layer</Badge>
              </div>

              <div className="space-y-3">
                {objects.map((object) => (
                  <div key={object.id} className="rounded-[18px] border border-slate-800 bg-slate-950/60 p-3">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium uppercase tracking-[0.2em] text-slate-400">{object.id}</span>
                        <span className="font-medium text-slate-100">{object.label}</span>
                      </div>
                      <Badge tone={object.risk === 'High' ? 'crimson' : object.risk === 'Medium' ? 'amber' : 'lime'}>{object.risk}</Badge>
                    </div>
                    <div className="mt-2 flex items-center justify-between text-xs uppercase tracking-[0.16em] text-slate-400">
                      <span>{object.distance}</span>
                      <span>{object.priority}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}

export default App;
