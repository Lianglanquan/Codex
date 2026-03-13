"use client";

import { FormEvent, useState } from "react";

type JobRecord = {
  job_id: string;
  status: string;
  runtime_notes: string[];
  artifacts: {
    run_dir: string;
    delivery?: string | null;
  };
  delivery?: {
    summary: string;
    outcome: string;
    reviewer_decision: string;
    gate_report_path: string;
    remaining_gaps: string[];
  } | null;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Page() {
  const [prompt, setPrompt] = useState("把这项任务从我身上拿走，并给我一个可直接验收的结果。");
  const [background, setBackground] = useState("任务背景、上下文、约束和现状。");
  const [offload, setOffload] = useState("我不想自己来回沟通、盯进度、补细节、做复查。");
  const [deliverable, setDeliverable] = useState("最终只给我结论、证据、风险和下一步。");
  const [mode, setMode] = useState<"auto" | "dry-run">("auto");
  const [result, setResult] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${apiBaseUrl}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job: prompt,
          background,
          offload,
          deliverable,
          mode,
        }),
      });

      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }

      const payload = (await response.json()) as JobRecord;
      setResult(payload);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "提交失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Codex CLI + Agents SDK</p>
        <h1>老板模式交付台</h1>
        <p className="lede">
          不是通用 agent 平台，而是你个人的任务抽离驾驶舱。你给目标和边界，系统负责派工、盯质量、收口证据。
        </p>
      </section>

      <section className="panel composer">
        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>目标</span>
            <textarea
              rows={4}
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="一句话说清你要什么结果"
            />
          </label>

          <label className="field">
            <span>背景</span>
            <textarea
              rows={4}
              value={background}
              onChange={(event) => setBackground(event.target.value)}
              placeholder="补充上下文、现状、限制条件"
            />
          </label>

          <label className="field">
            <span>你不想亲自做什么</span>
            <textarea
              rows={3}
              value={offload}
              onChange={(event) => setOffload(event.target.value)}
              placeholder="写明你要从哪些繁重事务里抽离出来"
            />
          </label>

          <label className="field">
            <span>最终只想看到什么</span>
            <textarea
              rows={3}
              value={deliverable}
              onChange={(event) => setDeliverable(event.target.value)}
              placeholder="例如：结论、证据、风险、待你决策的一项"
            />
          </label>

          <div className="controls">
            <label className="field mode-field">
              <span>运行模式</span>
              <select value={mode} onChange={(event) => setMode(event.target.value as "auto" | "dry-run")}>
                <option value="auto">auto</option>
                <option value="dry-run">dry-run</option>
              </select>
            </label>

            <button type="submit" disabled={busy}>
              {busy ? "派发中..." : "一键交付"}
            </button>
          </div>
        </form>
      </section>

      <section className="grid">
        <article className="panel metric">
          <h2>执行模式</h2>
          <p>{mode}</p>
        </article>
        <article className="panel metric">
          <h2>API</h2>
          <p>{apiBaseUrl}</p>
        </article>
        <article className="panel metric">
          <h2>老板视角</h2>
          <p>只看结论、证据、风险、回滚，不看 agent 之间的废话。</p>
        </article>
      </section>

      {error ? (
        <section className="panel error-card">
          <h2>提交失败</h2>
          <p>{error}</p>
        </section>
      ) : null}

      {result ? (
        <section className="panel result-card">
          <div className="result-header">
            <div>
              <p className="eyebrow">Run {result.job_id}</p>
              <h2>{result.delivery?.summary ?? "交付结果已生成"}</h2>
            </div>
            <span className={`status-pill status-${result.status}`}>{result.status}</span>
          </div>

          <div className="result-grid">
            <div>
              <h3>结果</h3>
              <p>Outcome: {result.delivery?.outcome ?? "unknown"}</p>
              <p>Reviewer: {result.delivery?.reviewer_decision ?? "unknown"}</p>
            </div>
            <div>
              <h3>路径</h3>
              <p>{result.artifacts.run_dir}</p>
              <p>{result.delivery?.gate_report_path ?? "无 gate report"}</p>
            </div>
          </div>

          {result.runtime_notes.length > 0 ? (
            <div className="notes">
              <h3>运行备注</h3>
              <ul>
                {result.runtime_notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {result.delivery?.remaining_gaps?.length ? (
            <div className="notes">
              <h3>剩余缺口</h3>
              <ul>
                {result.delivery.remaining_gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : (
        <section className="panel empty-card">
          <h2>等待任务</h2>
          <p>提交后会生成 `runs/&lt;id&gt;/` 下的一组工件，并尽量把你从沟通、催办、复查里抽离出来。</p>
        </section>
      )}
    </main>
  );
}
