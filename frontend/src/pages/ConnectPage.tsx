import { useEffect, useState } from 'react';
import { CheckIcon, CopyIcon, PlugIcon, TerminalIcon } from 'lucide-react';
import { getMcpInfo } from '../services/api';
import { Skeleton } from '../components/common/Skeleton';
import type { McpInfo } from '../types/api';

const WHY = [
{
  title: 'A crew desk does not want another tab',
  body:
  'Controllers already work across several screens — that is the problem this advisor ' +
  'exists to reduce. This console is a good screen, but it is still one more. MCP lets ' +
  'the advisor appear inside whatever the controller already has open.'
},
{
  title: 'It makes this a system of action, not a demo',
  body:
  'The same engine that answers this console can answer an ops assistant, a scheduling ' +
  'tool, or an agent nobody has written yet. We did not have to predict the client to ' +
  'serve it.'
},
{
  title: 'It is the shape the market already buys',
  body:
  'Airlines are funding MCP-exposed crew tooling today for qualifications and pay. What ' +
  'nobody has put behind that interface is the recovery reasoning — consequence ' +
  'traversal, ranked legal options, cost. That is the layer this adds.'
},
{
  title: 'It costs almost nothing to maintain',
  body:
  'The MCP server holds no logic. Every tool is a two-line wrapper forwarding to the ' +
  'same dispatch the REST API calls, and a test asserts both doors return identical ' +
  'answers, so they cannot drift apart.'
}];


function CopyButton({ text, label }: {text: string;label: string;}) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
        } catch {
          setCopied(false);
        }
      }}
      className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 text-xs font-semibold text-accent-ink transition-colors duration-150 ease-out hover:bg-accent-strong">

      {copied ?
      <CheckIcon aria-hidden="true" className="h-3.5 w-3.5" /> :
      <CopyIcon aria-hidden="true" className="h-3.5 w-3.5" />}
      {copied ? 'Copied' : label}
    </button>);

}

export function ConnectPage() {
  const [info, setInfo] = useState<McpInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getMcpInfo().
    then((res) => {
      if (active) setInfo(res);
    }).
    catch(() => {
      if (active) setError('Connection details are unavailable. Is the advisor running?');
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="mx-auto w-full max-w-page px-5 py-8">
      <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tightest text-fg">
        <PlugIcon aria-hidden="true" className="h-5 w-5 text-accent" />
        Connect over MCP
      </h1>
      <p className="mt-1 max-w-console text-sm text-fg-muted">
        The advisor answers this console over HTTP and any MCP client over stdio — the same
        engine behind both. Point Claude Desktop, an IDE or another agent at it and ask crew
        questions without leaving the tool you are already in.
      </p>

      {error &&
      <p className="mt-6 rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
          {error}
        </p>
      }

      {!info && !error &&
      <div className="mt-6 space-y-3" role="status" aria-live="polite">
          <span className="sr-only">Loading connection details</span>
          <Skeleton className="h-40 w-full rounded-md" />
          <Skeleton className="h-64 w-full rounded-md" />
        </div>
      }

      {info &&
      <>
          {/* ---------- why ---------- */}
          <section className="mt-8">
            <h2 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Why you would want this
            </h2>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {WHY.map((item) =>
            <div key={item.title} className="rounded-md border border-line bg-surface p-4">
                  <h3 className="text-sm font-semibold text-fg">{item.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-fg-muted">{item.body}</p>
                </div>
            )}
            </div>
          </section>

          {/* ---------- config ---------- */}
          <section className="mt-8">
            <h2 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
              Configuration for this machine
            </h2>
            <p className="mt-2 max-w-console text-sm text-fg-muted">
              These are the real paths on the machine the advisor is running on, so the
              block below can be pasted as-is. In Claude Desktop:{' '}
              <span className="text-fg">Settings → Developer → Edit Config</span>, or edit
              the file directly.
            </p>

            <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              <div className="rounded-md border border-line bg-surface px-3 py-2">
                <dt className="text-2xs uppercase tracking-label text-fg-faint">Windows</dt>
                <dd className="mt-0.5 break-all font-mono text-fg">{info.config_path.windows}</dd>
              </div>
              <div className="rounded-md border border-line bg-surface px-3 py-2">
                <dt className="text-2xs uppercase tracking-label text-fg-faint">macOS</dt>
                <dd className="mt-0.5 break-all font-mono text-fg">{info.config_path.macos}</dd>
              </div>
            </dl>

            <div className="mt-3 overflow-hidden rounded-md border border-line bg-sunken">
              <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
                <TerminalIcon aria-hidden="true" className="h-3.5 w-3.5 text-fg-faint" />
                <span className="text-2xs font-semibold uppercase tracking-label text-fg-muted">
                  claude_desktop_config.json
                </span>
                <span className="rounded-full border border-line-strong px-2 py-0.5 text-2xs text-fg-faint">
                  transport: {info.transport}
                </span>
                <div className="ml-auto">
                  <CopyButton text={info.config_json} label="Copy config" />
                </div>
              </div>
              <pre className="overflow-x-auto px-4 py-4 font-mono text-xs leading-relaxed text-fg">
                {info.config_json}
              </pre>
            </div>

            <ol className="mt-4 max-w-console list-decimal space-y-1.5 pl-5 text-sm text-fg-muted">
              <li>Paste the block into the config file above.</li>
              <li>
                <span className="text-fg">Quit the client fully</span> — on Windows, closing
                the window is not enough; quit from the tray icon. The config is read only
                at launch.
              </li>
              <li>
                Reopen it. <span className="font-mono text-fg">{info.server_name}</span>{' '}
                should appear in the tools list with {info.tools.length} tools.
              </li>
              <li>
                Ask:{' '}
                <span className="text-fg">
                  “Using {info.server_name}, Captain C-1042 just called in sick for tomorrow.
                  What should I do?”
                </span>
              </li>
            </ol>

            <p className="mt-3 max-w-console rounded-md border border-info-line bg-info-soft px-4 py-3 text-sm text-fg">
              This console does not need to be running. The client launches its own copy of
              the engine and talks to it over stdin/stdout, so MCP keeps working even with
              the API server stopped.
            </p>
          </section>

          {/* ---------- tools ---------- */}
          <section className="mt-8">
            <h2 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
              The {info.tools.length} tools exposed
            </h2>
            <p className="mt-2 max-w-console text-sm text-fg-muted">
              Generated from the same definitions the server registers, so this list cannot
              drift from the code. Every result carries its evidence — the facts used and
              where each came from — so a client can audit an answer, not just read it.
            </p>
            <div className="mt-3 overflow-x-auto rounded-md border border-line">
              <table className="w-full border-collapse text-sm">
                <caption className="sr-only">Tools exposed over MCP</caption>
                <thead>
                  <tr className="border-b border-line bg-surface">
                    <th scope="col" className="px-4 py-2 text-left text-2xs font-semibold uppercase tracking-label text-fg-faint">
                      Tool
                    </th>
                    <th scope="col" className="px-4 py-2 text-left text-2xs font-semibold uppercase tracking-label text-fg-faint">
                      Tier
                    </th>
                    <th scope="col" className="px-4 py-2 text-left text-2xs font-semibold uppercase tracking-label text-fg-faint">
                      What it returns
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {info.tools.map((tool) =>
                <tr key={tool.name} className="border-b border-line last:border-0">
                      <td className="whitespace-nowrap px-4 py-2 align-top font-mono text-xs text-fg">
                        {tool.name}
                      </td>
                      <td className="px-4 py-2 align-top">
                        <span className="rounded-full border border-line-strong px-2 py-0.5 font-mono text-2xs text-fg-muted">
                          T{tool.tier}
                        </span>
                      </td>
                      <td className="px-4 py-2 align-top text-sm leading-relaxed text-fg-muted">
                        {tool.description}
                      </td>
                    </tr>
                )}
                </tbody>
              </table>
            </div>
          </section>

          {/* ---------- troubleshooting ---------- */}
          <section className="mt-8 mb-4">
            <h2 className="text-2xs font-semibold uppercase tracking-label text-fg-faint">
              If it will not connect
            </h2>
            <dl className="mt-3 max-w-console space-y-3 text-sm">
              <div>
                <dt className="font-semibold text-fg">“Server disconnected” straight away</dt>
                <dd className="mt-1 leading-relaxed text-fg-muted">
                  Almost always the config. Use the absolute script path, not{' '}
                  <span className="font-mono text-fg">-m mcp_server.index</span>: Claude
                  Desktop does not apply a working directory, so the module form cannot
                  resolve the package and the process exits before it can explain itself.
                  The block above already uses the correct form.
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-fg">Nothing appears in the tools list</dt>
                <dd className="mt-1 leading-relaxed text-fg-muted">
                  The config is read at launch. Quit from the tray icon rather than closing
                  the window, then check Settings → Developer for the server’s output.
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-fg">“No operational database at …”</dt>
                <dd className="mt-1 leading-relaxed text-fg-muted">
                  Run <span className="font-mono text-fg">python scripts/import_data.py</span>.
                  The server checks at startup and says so rather than failing silently.
                </dd>
              </div>
            </dl>
          </section>
        </>
      }
    </main>);

}
