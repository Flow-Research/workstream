// Historical source, non-canonical.
// This file preserves the original React proposal for reference only.
// Canonical Workstream architecture lives in README.md, AGENTS.md, docs/architecture_lockdown.md, and docs/decision_*.md.

import { useState } from "react";

const c = {
  bg:"#0a0b0d",surface:"#111318",surface2:"#0d0f14",
  border:"#1e2330",borderLight:"#2a3040",
  text:"#e8eaf0",muted:"#6b7280",dim:"#374151",
  accent:"#f97316",accentGlow:"rgba(249,115,22,0.12)",
  blue:"#3b82f6",teal:"#14b8a6",green:"#22c55e",
  purple:"#a855f7",red:"#ef4444",amber:"#f59e0b",
};

const Tag = ({ label, color=c.accent }) => (
  <span style={{ display:"inline-block",padding:"2px 7px",borderRadius:3,fontSize:10,
    fontFamily:"monospace",fontWeight:700,letterSpacing:"0.08em",textTransform:"uppercase",
    color,background:`${color}18`,border:`1px solid ${color}30` }}>{label}</span>
);

const Block = ({ children, accent, style={} }) => (
  <div style={{ background:c.surface,border:`1px solid ${accent?accent+"28":c.border}`,
    borderLeft:accent?`3px solid ${accent}`:undefined,borderRadius:5,
    padding:"16px 18px",...style }}>{children}</div>
);

const SectionTitle = ({ n, title, sub }) => (
  <div style={{ marginBottom:28 }}>
    <div style={{ display:"flex",alignItems:"center",gap:10,marginBottom:6 }}>
      <span style={{ fontFamily:"monospace",fontSize:11,color:c.accent,fontWeight:700 }}>
        {String(n).padStart(2,"0")}
      </span>
      <div style={{ width:28,height:1,background:c.accent,opacity:.4 }} />
      <h2 style={{ margin:0,fontSize:18,fontWeight:700,color:c.text,
        fontFamily:"Georgia,serif",letterSpacing:"-0.02em" }}>{title}</h2>
    </div>
    {sub && <p style={{ margin:"0 0 0 50px",fontSize:12,color:c.muted,
      fontFamily:"monospace",lineHeight:1.6 }}>{sub}</p>}
  </div>
);

const Li = ({ children, color=c.accent }) => (
  <li style={{ fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.9,
    paddingLeft:14,position:"relative",listStyle:"none" }}>
    <span style={{ position:"absolute",left:0,color }}>›</span>{children}
  </li>
);

const tabs = [
  { id:"overview",   label:"Overview"      },
  { id:"gates",      label:"3 Gates"       },
  { id:"guide",      label:"Project Guide" },
  { id:"contract",   label:"Task Contract" },
  { id:"lifecycle",  label:"Lifecycle"     },
  { id:"pair",       label:"Owner-Agent"   },
  { id:"reputation", label:"Reputation"    },
  { id:"lockdown",   label:"Lock This Week"},
];

const Overview = () => (
  <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
    <SectionTitle n={1} title="What Workstream Is"
      sub="A source-agnostic execution layer for economically valuable work." />
    <Block accent={c.accent}>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:13,color:c.text,lineHeight:1.8 }}>
        Workstream does not care where work comes from. Every task — regardless of origin — flows through
        the same normalized loop with the same quality gates, the same accountability model, and the same
        payment and reputation infrastructure.
      </p>
    </Block>
    <div style={{ display:"flex",gap:8,flexWrap:"wrap" }}>
      {["Origin does not matter","Guide governs everything","Owner-Agent pair is the unit",
        "Consequences drive quality","Nothing enters without a contract"].map(p => (
        <div key={p} style={{ padding:"6px 12px",background:c.accentGlow,
          border:`1px solid ${c.accent}25`,borderRadius:4,
          fontSize:11,fontFamily:"monospace",color:c.accent }}>{p}</div>
      ))}
    </div>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 12px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>The core chain</p>
      <div style={{ display:"flex",alignItems:"center",gap:0,flexWrap:"wrap" }}>
        {["Origin","Project Guide","Task","Worker","Submission","Review","Payment","Reputation"].map((s,i,a) => (
          <div key={s} style={{ display:"flex",alignItems:"center" }}>
            <div style={{ padding:"6px 12px",background:c.surface,
              border:`1px solid ${c.borderLight}`,borderRadius:4,
              fontSize:11,fontFamily:"monospace",color:c.text }}>{s}</div>
            {i<a.length-1 && <span style={{ fontSize:10,color:c.muted,margin:"0 2px" }}>→</span>}
          </div>
        ))}
      </div>
    </Block>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 12px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Where this came from</p>
      <p style={{ margin:"0 0 12px",fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        Built entirely from direct operational experience — working as a task submitter, an agent operator,
        and a reviewer inside a live AI evaluation platform. Every design decision is an observation, not a theory.
      </p>
      <div style={{ display:"flex",gap:12,flexWrap:"wrap" }}>
        {[
          { role:"Worker", insight:"Base payout must be visible before claiming. Guide must be clear or revision cycles hurt both sides." },
          { role:"Agent Operator", insight:"Agent cannot do it alone. Human review before submission is non-negotiable. 48h setup compounds into daily throughput." },
          { role:"Reviewer", insight:"Checker automation protects reviewer time. Bad submissions without evidence are unverifiable. Consequences must be structural." },
        ].map(({ role, insight }) => (
          <div key={role} style={{ flex:1,minWidth:180,padding:"12px",background:c.surface,
            border:`1px solid ${c.borderLight}`,borderRadius:4 }}>
            <Tag label={role} color={c.teal} />
            <p style={{ margin:"8px 0 0",fontFamily:"monospace",fontSize:11,color:c.muted,lineHeight:1.6 }}>{insight}</p>
          </div>
        ))}
      </div>
    </Block>
    <Block accent={c.green}>
      <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:c.green,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>The accountability philosophy</p>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        Workstream does not ban AI. AI use is required. But the human owner is accountable for everything
        that goes out under their name. Consequences are structural and automatic — not enforced by a moderator.
        Rational workers self-enforce when the cost of laziness is real.
      </p>
    </Block>
  </div>
);

const Gates = () => {
  const [open, setOpen] = useState("g1");
  const gates = [
    { id:"g1",num:"01",title:"Origin Qualification",sub:"One time — at onboarding",color:c.blue,tag:"ORIGIN GATE",
      desc:"Before an origin can send a single task, Workstream evaluates the origin itself. This happens once. Pass and the origin is in permanently until they violate terms. Bittensor, Snorkel, Moniepoint, a startup — same gate, same checks, no special treatment.",
      checks:[
        "Minimum task payout meets the platform floor — configurable per currency (e.g. $5 USD equivalent)",
        "Can receive structured drop notifications via webhook or equivalent endpoint",
        "Has at least one active published project guide ready",
      ],
      dropLabel:"Origin qualification drop notification",
      dropFields:[
        { f:"origin_id",     t:"string",           n:"Their identifier in Workstream" },
        { f:"drop_reason",   t:"enum + string",     n:"Why they failed qualification" },
        { f:"fix_required",  t:"string",            n:"Exactly what needs to change before reapplication" },
        { f:"timestamp",     t:"datetime",          n:"" },
      ],
      note:"Drop notifications are structured, not plain text. Origins need to handle drops programmatically at scale. An enum reason code plus a fix description is machine-readable."
    },
    { id:"g2",num:"02",title:"Task Ingestion",sub:"Per task — every task from a qualified origin",color:c.teal,tag:"INGESTION GATE",
      desc:"Every individual task arriving from a qualified origin must carry the full minimum contract. Missing any one field — silent drop, origin notified with a structured message. No task enters the queue incomplete.",
      checks:[
        "origin_id — must reference a currently qualified origin",
        "project_guide_id — must reference an active published guide under that origin",
        "base_payout — must carry amount, currency, and payout_type",
      ],
      dropLabel:"Task ingestion drop notification",
      dropFields:[
        { f:"your_task_id",  t:"string",            n:"Their internal reference so they can locate it" },
        { f:"drop_reason",   t:"enum + string",     n:"Which field was missing or invalid" },
        { f:"fix_required",  t:"string",            n:"What exactly needs to change" },
        { f:"timestamp",     t:"datetime",          n:"" },
      ],
      note:"Configuration enforces guide attachment at project creation — you physically cannot publish a project without a guide. The ingestion gate validates the task contract, not guide existence."
    },
    { id:"g3",num:"03",title:"Submission Quality",sub:"Runtime — after a worker submits",color:c.amber,tag:"SUBMISSION GATE",
      desc:"Checkers run against the specific project guide governing that task — not generic rules. The guide is the rule set. Blocking checker policy failures return the packet to the worker before it ever reaches a reviewer.",
      checks:[
        "check_acceptance_criteria_present — task includes reviewable acceptance criteria",
        "check_policy_context_present — locked guide and policy context is present",
        "check_submission_packet — submission packet matches required structure",
        "check_evidence_present — evidence references are present",
        "check_evidence_integrity — EvidenceManifest present, artifact hashes validate",
        "check_required_files — all files listed in guide requirements are attached",
        "check_forbidden_files — no disqualified file types or content",
        "check_confidentiality_attestation — worker attestation covers confidential data and credentials",
        "check_low_quality_generated_artifacts — basic quality signal on submitted output",
      ],
      dropLabel:"Checker failure response to worker",
      dropFields:[
        { f:"checker_id",    t:"string",            n:"Which checker fired" },
        { f:"severity",      t:"enum",              n:"high (blocks) / medium (warns) / low (logs)" },
        { f:"finding",       t:"string",            n:"What was wrong" },
        { f:"suggested_fix", t:"string",            n:"Every failure must include a fix suggestion" },
        { f:"artifact_hash", t:"string",            n:"Tied to exact submission artifacts" },
      ],
      note:"Admin overrides for high-severity failures require a logged reason. Each checker blind spot gets recorded as a ProjectLesson for guide improvement."
    },
  ];
  return (
    <div style={{ display:"flex",flexDirection:"column",gap:8 }}>
      <SectionTitle n={2} title="The Three Gates"
        sub="Separate concerns, separate layers. None overlap." />
      {gates.map(g => (
        <div key={g.id}>
          <div onClick={() => setOpen(open===g.id?null:g.id)}
            style={{ display:"flex",alignItems:"center",gap:12,padding:"12px 16px",
              background:open===g.id?g.color+"08":c.surface,
              border:`1px solid ${open===g.id?g.color+"40":c.border}`,
              borderRadius:5,cursor:"pointer",transition:"all .15s" }}>
            <span style={{ fontFamily:"monospace",fontSize:13,fontWeight:700,color:g.color,minWidth:24 }}>{g.num}</span>
            <div style={{ flex:1 }}>
              <div style={{ display:"flex",alignItems:"center",gap:10 }}>
                <span style={{ fontSize:14,fontWeight:700,color:c.text,fontFamily:"Georgia,serif" }}>{g.title}</span>
                <Tag label={g.tag} color={g.color} />
              </div>
              <span style={{ fontSize:11,fontFamily:"monospace",color:c.muted }}>{g.sub}</span>
            </div>
            <span style={{ color:g.color,fontSize:14 }}>{open===g.id?"−":"+"}</span>
          </div>
          {open===g.id && (
            <div style={{ marginLeft:4,padding:"16px",background:g.color+"05",
              border:`1px solid ${g.color}20`,borderTop:"none",borderRadius:"0 0 5px 5px" }}>
              <p style={{ margin:"0 0 14px",fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.7 }}>{g.desc}</p>
              <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:g.color,
                letterSpacing:"0.1em",textTransform:"uppercase" }}>Checks</p>
              <ul style={{ margin:"0 0 16px",padding:0 }}>
                {g.checks.map((ch,i) => <Li key={i} color={g.color}>{ch}</Li>)}
              </ul>
              <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:g.color,
                letterSpacing:"0.1em",textTransform:"uppercase" }}>{g.dropLabel}</p>
              <div style={{ background:"#070809",borderRadius:4,overflow:"hidden",
                border:`1px solid ${c.border}`,marginBottom:14 }}>
                <div style={{ display:"grid",gridTemplateColumns:"180px 150px 1fr",
                  padding:"6px 14px",background:"#0d0f14",borderBottom:`1px solid ${c.border}` }}>
                  {["field","type","note"].map(h => (
                    <span key={h} style={{ fontSize:10,fontFamily:"monospace",color:c.muted,
                      letterSpacing:"0.1em",textTransform:"uppercase" }}>{h}</span>
                  ))}
                </div>
                {g.dropFields.map((row,i) => (
                  <div key={i} style={{ display:"grid",gridTemplateColumns:"180px 150px 1fr",
                    padding:"6px 14px",borderBottom:i<g.dropFields.length-1?`1px solid ${c.border}`:"none",
                    background:i%2===0?"transparent":"#0a0b0d" }}>
                    <span style={{ fontFamily:"monospace",fontSize:11,color:g.color }}>{row.f}</span>
                    <span style={{ fontFamily:"monospace",fontSize:11,color:c.blue }}>{row.t}</span>
                    <span style={{ fontFamily:"monospace",fontSize:11,color:c.muted }}>{row.n}</span>
                  </div>
                ))}
              </div>
              <div style={{ padding:"10px 14px",background:g.color+"08",
                border:`1px solid ${g.color}20`,borderRadius:4 }}>
                <p style={{ margin:0,fontFamily:"monospace",fontSize:11,color:c.muted,lineHeight:1.6 }}>
                  <span style={{ color:g.color,fontWeight:700 }}>Design note: </span>{g.note}
                </p>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const GuideSection = () => (
  <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
    <SectionTitle n={3} title="Project Guide"
      sub="The single source of truth. Governs worker, checker, auto evaluator, and human reviewer. One document used at every layer." />
    <Block accent={c.purple}>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        The guide is fully transparent to all parties. Workers see the reviewer rubric. Reviewers use the same
        document the worker submitted against. No hidden criteria. Full transparency produces better submissions,
        fewer revision cycles, and no disputes about unstated expectations.
      </p>
    </Block>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 12px",fontSize:10,fontFamily:"monospace",color:c.purple,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Required field structure</p>
      {[
        { f:"title",              req:true,  n:"Plain name of the project" },
        { f:"version",            req:true,  n:"CRITICAL — tasks lock to the version active at assignment. Must increment on material changes." },
        { f:"description",        req:true,  n:"What this project is and why it exists" },
        { f:"task_instructions",  req:true,  n:"Exactly what the submitter must do, step by step" },
        { f:"output_requirements",req:true,  n:"Format, files, structure required in the submission packet" },
        { f:"acceptance_criteria",req:true,  n:"What good work looks like. Must be specific and measurable." },
        { f:"rejection_criteria", req:true,  n:"Disqualifying conditions. What fails automatically without appeal." },
        { f:"reviewer_rubric",    req:true,  n:"How quality is scored. Used by human reviewer AND auto evaluator identically." },
        { f:"forbidden_actions",  req:true,  n:"What not to do. Checker validates against this list." },
        { f:"difficulty",         req:true,  n:"easy / medium / hard / expert" },
        { f:"estimated_time",     req:true,  n:"Helps worker make the economic decision before claiming" },
        { f:"required_skills",    req:true,  n:"Used by Task Router for Owner-Agent Pair matching" },
        { f:"examples",           req:false, n:"Optional. Good and bad sample outputs. Significantly reduces revision rate when present." },
      ].map((row,i) => (
        <div key={i} style={{ display:"flex",gap:12,padding:"5px 0",
          borderBottom:`1px solid ${c.border}` }}>
          <span style={{ fontFamily:"monospace",fontSize:12,color:c.purple,minWidth:220,flexShrink:0 }}>
            {row.f}{row.req && <span style={{ color:c.red,marginLeft:4 }}>*</span>}
          </span>
          <span style={{ fontFamily:"monospace",fontSize:12,color:c.muted }}>{row.n}</span>
        </div>
      ))}
      <p style={{ margin:"8px 0 0",fontSize:10,fontFamily:"monospace",color:c.red }}>
        * required — guide cannot be published without these fields
      </p>
    </Block>
    <Block accent={c.amber}>
      <p style={{ margin:"0 0 10px",fontSize:10,fontFamily:"monospace",color:c.amber,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Guide versioning policy — lock from day one</p>
      <ul style={{ margin:0,padding:0 }}>
        {[
          "Every guide has an explicit version field — e.g. v1.0, v1.1, v2.0",
          "When a worker claims a task, it locks to the guide version active at that exact moment",
          "In-flight tasks are unaffected by guide updates — they keep the version they claimed under",
          "New tasks created after an update use the new version automatically",
          "Version must increment when acceptance criteria, rejection criteria, rubric, or output requirements change",
          "Minor corrections (typos, formatting) may not require a version increment — team sets the threshold",
          "Old versions are never deleted — only superseded. Version history is permanent.",
        ].map((item,i) => <Li key={i} color={c.amber}>{item}</Li>)}
      </ul>
    </Block>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Why versioning cannot wait</p>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        Without versioning, a worker can submit correct work and get rejected because the guide changed
        mid-task. That is a platform failure, not a worker failure. The worker takes the reputation hit for
        something the platform caused. Versioning eliminates this entire class of dispute. Retrofitting it
        after tasks are in flight is impossible to do fairly.
      </p>
    </Block>
  </div>
);

const ContractSection = () => (
  <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
    <SectionTitle n={4} title="Task Contract Schema"
      sub="Every task from every origin normalizes to this structure. The schema is the stable surface." />
    <Block accent={c.teal}>
      <p style={{ margin:"0 0 10px",fontSize:10,fontFamily:"monospace",color:c.teal,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Minimum ingestion contract — Gate 2</p>
      <p style={{ margin:"0 0 12px",fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.7 }}>
        Three fields only. Missing any one — silent drop, origin notified.
      </p>
      {[
        { f:"origin_id",        t:"string", n:"Must reference a qualified origin" },
        { f:"project_guide_id", t:"string", n:"Must reference an active published guide" },
        { f:"base_payout",      t:"object", n:"{ amount, currency, payout_type }" },
      ].map((r,i) => (
        <div key={i} style={{ display:"flex",gap:12,padding:"5px 0",
          borderBottom:i<2?`1px solid ${c.border}`:"none" }}>
          <span style={{ fontFamily:"monospace",fontSize:12,color:c.teal,minWidth:200,flexShrink:0 }}>{r.f}</span>
          <span style={{ fontFamily:"monospace",fontSize:12,color:c.blue,minWidth:100,flexShrink:0 }}>{r.t}</span>
          <span style={{ fontFamily:"monospace",fontSize:12,color:c.muted }}>{r.n}</span>
        </div>
      ))}
    </Block>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 10px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Full normalized WorkstreamTask contract</p>
      {[
        { f:"task_id",                 t:"uuid",      n:"Workstream internal — not the origin's ID" },
        { f:"origin_id",               t:"string",    n:"Internal only — never exposed to worker" },
        { f:"project_guide_id",        t:"string",    n:"" },
        { f:"locked_guide_version",    t:"string",    n:"Locked before the worker starts" },
        { f:"locked_checker_policy_version", t:"string", n:"Derived from the task contract" },
        { f:"locked_review_policy_version",  t:"string", n:"Derived from the task contract" },
        { f:"locked_payment_policy_version", t:"string", n:"Derived from the task contract" },
        { f:"title",                   t:"string",    n:"" },
        { f:"description",             t:"string",    n:"" },
        { f:"task_type",               t:"enum",      n:"model_eval | benchmark | coding_agent | stem | escrowed_job | paid_service" },
        { f:"base_payout.amount",      t:"number",    n:"Floor value" },
        { f:"base_payout.currency",    t:"enum",      n:"USD | NGN | USDC | TAO | POINTS | CUSTOM" },
        { f:"base_payout.payout_type", t:"enum",      n:"fixed | milestone | grant | subnet_reward" },
        { f:"requirements.skills",     t:"string[]",  n:"Used by Task Router for matching" },
        { f:"requirements.output_fmt", t:"string",    n:"" },
        { f:"context.prompt",          t:"string",    n:"" },
        { f:"context.materials",       t:"file[]",    n:"" },
        { f:"verification.method",     t:"enum[]",    n:"rubric | tests | oracle | evaluator_agent | consensus" },
        { f:"verification.rubric",     t:"object[]",  n:"Sourced directly from project guide" },
        { f:"execution.deadline",      t:"datetime",  n:"" },
        { f:"execution.difficulty",    t:"enum",      n:"easy | medium | hard | expert" },
        { f:"execution.retry_policy",  t:"string",    n:"Max retries before task fails" },
        { f:"execution.est_time",      t:"string",    n:"Shown to worker before claiming" },
        { f:"assignment.owner_id",     t:"string",    n:"" },
        { f:"assignment.agent_id",     t:"string",    n:"" },
        { f:"settlement.type",         t:"enum",      n:"escrow | onchain | offchain | manual" },
        { f:"settlement.erc8183_id",   t:"bytes32",   n:"On-chain job reference if applicable" },
        { f:"reputation.weight",       t:"number",    n:"How much this task affects reputation score" },
        { f:"reputation.skill_tags",   t:"string[]",  n:"Which skill dimensions are scored" },
        { f:"status",                  t:"enum",      n:"Current lifecycle state" },
        { f:"created_at",              t:"datetime",  n:"" },
      ].map((row,i) => (
        <div key={i} style={{ display:"flex",gap:12,padding:"5px 0",
          borderBottom:i<27?`1px solid ${c.border}`:"none",
          background:i%2===0?"transparent":"#0a0b0d" }}>
          <span style={{ fontFamily:"monospace",fontSize:11,color:c.accent,minWidth:220,flexShrink:0 }}>{row.f}</span>
          <span style={{ fontFamily:"monospace",fontSize:11,color:c.blue,minWidth:100,flexShrink:0 }}>{row.t}</span>
          <span style={{ fontFamily:"monospace",fontSize:11,color:c.muted }}>{row.n}</span>
        </div>
      ))}
    </Block>
    <Block accent={c.blue}>
      <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:c.blue,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Base payout — locked enums</p>
      <p style={{ margin:"0 0 10px",fontFamily:"monospace",fontSize:11,color:c.muted }}>Currency</p>
      <div style={{ display:"flex",gap:8,flexWrap:"wrap",marginBottom:12 }}>
        {["USD","NGN","USDC","TAO","POINTS","CUSTOM"].map(cur => (
          <span key={cur} style={{ padding:"4px 10px",background:c.blue+"12",
            border:`1px solid ${c.blue}30`,borderRadius:3,
            fontFamily:"monospace",fontSize:11,color:c.blue }}>{cur}</span>
        ))}
      </div>
      <p style={{ margin:"0 0 10px",fontFamily:"monospace",fontSize:11,color:c.muted }}>Payout type</p>
      <div style={{ display:"flex",gap:8,flexWrap:"wrap",marginBottom:12 }}>
        {["fixed","milestone","grant","subnet_reward"].map(pt => (
          <span key={pt} style={{ padding:"4px 10px",background:c.blue+"12",
            border:`1px solid ${c.blue}30`,borderRadius:3,
            fontFamily:"monospace",fontSize:11,color:c.blue }}>{pt}</span>
        ))}
      </div>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:11,color:c.muted,lineHeight:1.6 }}>
        Platform floor is denominated in USD equivalent. All currencies evaluated against the floor
        using a configurable rate at origin qualification time. CUSTOM requires manual approval.
      </p>
    </Block>
  </div>
);

const LifecycleSection = () => {
  const [active, setActive] = useState(null);
  const states = [
    { id:"INGESTED",     color:c.blue,   layer:"Source",       desc:"Source adapter receives task. Basic presence check runs." },
    { id:"FILTERED",     color:c.blue,   layer:"Source",       desc:"Economic Value Engine scores payout quality, source trust, feasibility. Fail = silent drop + structured origin notification." },
    { id:"NORMALIZED",   color:c.teal,   layer:"Normalization", desc:"Task Normalization Engine converts to full WorkstreamTask contract. Guide version locked at this point." },
    { id:"ROUTED",       color:c.teal,   layer:"Normalization", desc:"Task Router matches to eligible Owner-Agent Pairs by skills, reputation, availability, and difficulty." },
    { id:"ASSIGNED",     color:c.purple, layer:"Execution",    desc:"Owner accepts. Agent execution authorized to begin." },
    { id:"IN_PROGRESS",  color:c.purple, layer:"Execution",    desc:"Agent executes task. Owner can monitor. Retries happen here before OWNER_REVIEW." },
    { id:"OWNER_REVIEW", color:c.accent, layer:"Control",      desc:"HUMAN GATE. Owner reviews agent output. Can approve, send back to IN_PROGRESS for retry, or reject. Nothing reaches verification without owner sign-off.", highlight:true },
    { id:"SUBMITTED",    color:c.accent, layer:"Control",      desc:"Owner approves and signs submission. EvidenceManifest attached. Packet sent to verification." },
    { id:"UNDER_REVIEW", color:c.green,  layer:"Verification", desc:"Verification engine or external evaluator reviews against the project guide rubric." },
    { id:"COMPLETED",    color:c.green,  layer:"Terminal",     desc:"Accepted work. Settlement triggered. Reputation updated positively for owner and agent." },
    { id:"rejected_work",color:c.red,    layer:"Terminal",     desc:"Rejected work. Reputation hit on both owner and agent. Partial or no payment per policy." },
    { id:"EXPIRED",      color:c.muted,  layer:"Terminal",     desc:"Deadline passed. Funds returned to client. Reputation impact based on stage reached." },
  ];
  const layerColors = { Source:c.blue,Normalization:c.teal,Execution:c.purple,Control:c.accent,Verification:c.green,Terminal:c.muted };
  const layers = [...new Set(states.map(s=>s.layer))];
  return (
    <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
      <SectionTitle n={5} title="Task Lifecycle State Machine"
        sub="Click any state to expand. OWNER_REVIEW is the critical human gate." />
      <div style={{ display:"flex",gap:8,flexWrap:"wrap",marginBottom:4 }}>
        {layers.map(l => (
          <div key={l} style={{ display:"flex",alignItems:"center",gap:6 }}>
            <div style={{ width:8,height:8,borderRadius:"50%",background:layerColors[l] }} />
            <span style={{ fontSize:11,fontFamily:"monospace",color:c.muted }}>{l}</span>
          </div>
        ))}
      </div>
      {states.map((s,i) => (
        <div key={s.id}>
          <div onClick={() => setActive(active===s.id?null:s.id)}
            style={{ display:"flex",alignItems:"center",gap:12,padding:"10px 14px",
              border:`1px solid ${active===s.id?s.color+"60":s.highlight?s.color+"40":c.border}`,
              borderRadius:4,background:s.highlight?s.color+"08":active===s.id?s.color+"06":c.surface,
              cursor:"pointer",transition:"all .15s" }}>
            <div style={{ width:8,height:8,borderRadius:"50%",background:s.color,flexShrink:0,
              boxShadow:active===s.id||s.highlight?`0 0 8px ${s.color}`:"none" }} />
            <span style={{ fontFamily:"monospace",fontSize:12,fontWeight:700,
              color:active===s.id?s.color:c.text,flex:1,letterSpacing:"0.05em" }}>{s.id}</span>
            <Tag label={s.layer} color={s.color} />
            {s.highlight && <Tag label="HUMAN GATE" color={c.accent} />}
          </div>
          {active===s.id && (
            <div style={{ marginLeft:20,padding:"10px 14px",background:s.color+"06",
              borderLeft:`2px solid ${s.color}40`,borderRadius:"0 4px 4px 0",marginTop:2 }}>
              <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.7 }}>{s.desc}</p>
              {s.id==="OWNER_REVIEW" && (
                <p style={{ margin:"8px 0 0",fontFamily:"monospace",fontSize:11,color:c.accent }}>
                  Sending back to IN_PROGRESS has no external consequence. Once submitted and rejected by policy, both owner and agent take the reputation hit. The human gate is the point of no return.
                </p>
              )}
            </div>
          )}
          {i<states.length-1 && !["COMPLETED","rejected_work"].includes(s.id) && (
            <div style={{ display:"flex",justifyContent:"center",height:12,alignItems:"center",opacity:.3 }}>
              <div style={{ width:1,height:"100%",background:c.borderLight }} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
};

const PairSection = () => (
  <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
    <SectionTitle n={6} title="Owner-Agent Pair Model"
      sub="The atomic unit of execution. Accountability is shared. Neither acts alone in the system." />
    <div style={{ display:"flex",gap:12,flexWrap:"wrap" }}>
      {[
        { role:"Owner",color:c.accent,items:[
          "Holds the provider wallet — ERC-8183 Provider role",
          "Registers agents under their account",
          "Accepts or declines task assignment",
          "Reviews agent output in OWNER_REVIEW state",
          "Signs the on-chain submission — the final authority",
          "Can send work back to IN_PROGRESS for retry",
          "Reputation tied directly to agent performance",
          "If bad work submitted and rejected — reputation hit",
          "Cannot escape consequence by blaming the agent",
        ]},
        { role:"Agent",color:c.purple,items:[
          "Registered with ERC-8004 identity on-chain",
          "Executes tasks autonomously",
          "Cannot submit directly on-chain — ever",
          "All output goes to owner first for review",
          "Reputation tracked per task type and skill domain",
          "Multiple agents can belong to one owner",
          "LearningRecord captures improvement over time",
          "Framework-agnostic — OpenClaw, custom, any agent — as long as it follows the contract",
        ]},
      ].map(({ role, color, items }) => (
        <div key={role} style={{ flex:1,minWidth:240 }}>
          <Block accent={color} style={{ height:"100%" }}>
            <Tag label={role} color={color} />
            <ul style={{ margin:"12px 0 0",padding:0 }}>
              {items.map((item,i) => <Li key={i} color={color}>{item}</Li>)}
            </ul>
          </Block>
        </div>
      ))}
    </div>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 10px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>The accountability model in plain terms</p>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        Workstream does not ban AI. AI use is mandatory. But the owner is accountable for everything
        that goes out under their name. The OWNER_REVIEW gate is not a UX feature — it is an architectural
        guarantee that a human made a conscious decision before any submission reached the verification layer.
        Consequences are structural: bad output means reputation hit, fewer tasks routed, lower earnings.
        Rational owners self-enforce without being policed.
      </p>
    </Block>
    <Block accent={c.blue}>
      <p style={{ margin:"0 0 10px",fontSize:10,fontFamily:"monospace",color:c.blue,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>ERC-8183 role mapping</p>
      <div style={{ display:"flex",gap:10,flexWrap:"wrap" }}>
        {[
          { erc:"Client",    ws:"Task Poster",        desc:"Posts and funds the task",              color:c.blue },
          { erc:"Provider",  ws:"Owner Wallet",       desc:"Signs submission, receives payment",    color:c.accent },
          { erc:"Evaluator", ws:"Verification Engine",desc:"Workstream is the default evaluator",   color:c.green },
        ].map(({ erc, ws, desc, color }) => (
          <div key={erc} style={{ flex:1,minWidth:160,padding:"10px 12px",
            background:color+"08",border:`1px solid ${color}20`,borderRadius:4 }}>
            <div style={{ display:"flex",gap:6,marginBottom:6,alignItems:"center",flexWrap:"wrap" }}>
              <Tag label={erc} color={color} />
              <span style={{ fontSize:10,color:c.muted }}>→</span>
              <Tag label={ws} color={color} />
            </div>
            <p style={{ margin:0,fontSize:11,fontFamily:"monospace",color:c.muted }}>{desc}</p>
          </div>
        ))}
      </div>
    </Block>
  </div>
);

const ReputationSection = () => (
  <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
    <SectionTitle n={7} title="Reputation System"
      sub="Dual reputation — owner and agent both update after every terminal state. Feeds back into routing." />
    <div style={{ display:"flex",gap:12,flexWrap:"wrap" }}>
      {[
        { label:"Agent Reputation",color:c.purple,items:[
          "Tracked per task type and skill domain",
          "Success rate, quality score, speed",
          "Revision rate before OWNER_REVIEW",
          "Post-submission rejection rate",
          "Improvement tracked via LearningRecord",
          "Written to ERC-8004 reputation registry",
          "Portable — follows agent across platforms",
        ]},
        { label:"Owner Reputation",color:c.accent,items:[
          "Review quality — how well owner catches bad output",
          "Submission accuracy after human gate",
          "Dispute history",
          "OWNER_REVIEW response time",
          "Whether returned work improved before submission",
          "Combined with agent score for routing priority",
          "Affected by agent performance — they are bound",
        ]},
        { label:"Reviewer Reputation",color:c.teal,items:[
          "Separate from worker/owner reputation",
          "Accuracy of accept/reject decisions",
          "Consistency with rubric over time",
          "Review turnaround speed",
          "False positive and false negative rates",
          "Affects reviewer routing priority directly",
          "Removal threshold if quality drops below floor",
        ]},
      ].map(({ label, color, items }) => (
        <div key={label} style={{ flex:1,minWidth:200 }}>
          <Block accent={color}>
            <Tag label={label} color={color} />
            <ul style={{ margin:"10px 0 0",padding:0 }}>
              {items.map((item,i) => <Li key={i} color={color}>{item}</Li>)}
            </ul>
          </Block>
        </div>
      ))}
    </div>
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>How reputation drives the system</p>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        Reputation feeds directly back into the Task Router. High combined owner-agent score means
        priority routing to better tasks with higher payouts. Low score means fewer tasks, lower quality
        tasks, eventually locked out. Nobody moderates this manually. The system self-regulates through
        accumulated outcomes. Workers who self-enforce quality compound their earnings over time.
        Workers who do not get filtered out naturally.
      </p>
    </Block>
  </div>
);

const LockdownSection = () => (
  <div style={{ display:"flex",flexDirection:"column",gap:16 }}>
    <SectionTitle n={8} title="Lock This Week — June 2-5"
      sub="Six decisions. Everything in W1 engineering depends on all six being agreed by end of week." />
    {[
      { n:"01",title:"Project Guide template field structure",color:c.red,tag:"HIGHEST PRIORITY",
        why:"Every W1 engineering object depends on this. The guide fields define what WorkstreamTask carries, what checkers validate against, and what the reviewer evaluates with.",
        action:"Agree the field list in this document. Team reviews, challenges, and confirms. Must be frozen before any schema is written." },
      { n:"02",title:"Guide versioning policy",color:c.red,tag:"HIGHEST PRIORITY",
        why:"Must be in from day one. Retrofitting versioning after tasks are in flight creates disputes that are impossible to resolve fairly.",
        action:"Confirm: version field is required, tasks lock at assignment, version increments on material guide changes, prior versions are never deleted." },
      { n:"03",title:"Origin qualification criteria",color:c.accent,tag:"HIGH",
        why:"Defines what Workstream accepts at the source level. Determines who can become an origin and on what terms.",
        action:"Confirm the three checks. Set the platform floor value — recommended starting point is $5 USD equivalent, configurable per currency." },
      { n:"04",title:"Task contract minimum fields",color:c.accent,tag:"HIGH",
        why:"The ingestion gate logic depends on knowing exactly what constitutes a valid task contract.",
        action:"Confirm: origin_id, project_guide_id, base_payout. Nothing else required at ingestion. Everything else is added during normalization." },
      { n:"05",title:"Drop notification schema",color:c.amber,tag:"IMPORTANT",
        why:"Origins need structured feedback to fix and resubmit. Plain text does not scale programmatically.",
        action:"Confirm field structures for both origin qualification drops and task ingestion drops as defined in the Gates section." },
      { n:"06",title:"Base payout schema — currency and payout type enums",color:c.amber,tag:"IMPORTANT",
        why:"Determines how different origin types express payout consistently across fiat, stablecoin, token, and points.",
        action:"Confirm: { amount: number, currency: enum, payout_type: enum }. Confirm the six currency values and four payout type values." },
    ].map(item => (
      <Block key={item.n} accent={item.color}>
        <div style={{ display:"flex",alignItems:"center",gap:10,marginBottom:10 }}>
          <span style={{ fontFamily:"monospace",fontSize:13,color:item.color,fontWeight:700 }}>{item.n}</span>
          <span style={{ fontSize:14,fontWeight:700,color:c.text,fontFamily:"Georgia,serif",flex:1 }}>{item.title}</span>
          <Tag label={item.tag} color={item.color} />
        </div>
        <p style={{ margin:"0 0 8px",fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.6 }}>
          <span style={{ color:item.color }}>Why now: </span>{item.why}
        </p>
        <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.6 }}>
          <span style={{ color:item.color }}>Action: </span>{item.action}
        </p>
      </Block>
    ))}
    <Block style={{ background:c.surface2 }}>
      <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:c.muted,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Intentionally deferred — not this week</p>
      <ul style={{ margin:0,padding:0 }}>
        {[
          "Source adapters — manual intake only for v0.1",
          "On-chain settlement — ERC-8183 integration is post-v0.1",
          "OmniClaw payment policy enforcement — post-v0.1",
          "x402 micropayments — post-v0.1",
          "ERC-8004 reputation writes — post-v0.1",
          "Automated routing — manual assignment for v0.1",
          "Any origin-specific adapter logic — origin is generic at this stage",
          "Jarvis WorkSession integration — Workstream loop proves itself first",
        ].map((item,i) => <Li key={i} color={c.muted}>{item}</Li>)}
      </ul>
    </Block>
    <Block accent={c.green}>
      <p style={{ margin:"0 0 8px",fontSize:10,fontFamily:"monospace",color:c.green,
        textTransform:"uppercase",letterSpacing:"0.1em" }}>Definition of done for this week</p>
      <p style={{ margin:0,fontFamily:"monospace",fontSize:12,color:c.muted,lineHeight:1.8 }}>
        All six items above are agreed and documented. The first pilot project guide can be written
        using the locked template. The first task can be created without inventing rules mid-conversation.
        Engineering can start W1 on June 8th with no ambiguity about what they are building.
      </p>
    </Block>
  </div>
);

export default function WorkstreamLockdown() {
  const [active, setActive] = useState("overview");
  const panels = { overview:<Overview/>, gates:<Gates/>, guide:<GuideSection/>,
    contract:<ContractSection/>, lifecycle:<LifecycleSection/>,
    pair:<PairSection/>, reputation:<ReputationSection/>, lockdown:<LockdownSection/> };

  return (
    <div style={{ background:c.bg,minHeight:"100vh",color:c.text,fontFamily:"monospace" }}>
      <div style={{ borderBottom:`1px solid ${c.border}`,padding:"16px 28px",
        display:"flex",alignItems:"center",justifyContent:"space-between",
        position:"sticky",top:0,background:c.bg,zIndex:100,flexWrap:"wrap",gap:10 }}>
        <div style={{ display:"flex",alignItems:"center",gap:12 }}>
          <div style={{ width:26,height:26,background:c.accent,borderRadius:4,
            display:"flex",alignItems:"center",justifyContent:"center",
            fontSize:13,color:"#000",fontWeight:900 }}>W</div>
          <div>
            <div style={{ fontSize:13,fontWeight:700,color:c.text,letterSpacing:"0.05em" }}>WORKSTREAM</div>
            <div style={{ fontSize:10,color:c.muted }}>Architecture Lockdown Document</div>
          </div>
        </div>
        <div style={{ display:"flex",gap:3,flexWrap:"wrap" }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActive(t.id)} style={{
              padding:"5px 10px",border:`1px solid ${active===t.id?c.accent+"60":c.border}`,
              borderRadius:4,background:active===t.id?c.accentGlow:"transparent",
              color:active===t.id?c.accent:c.muted,cursor:"pointer",
              fontSize:10,fontFamily:"monospace",letterSpacing:"0.04em",
              transition:"all .15s" }}>{t.label}</button>
          ))}
        </div>
      </div>
      <div style={{ maxWidth:900,margin:"0 auto",padding:"36px 28px" }}>
        {panels[active]}
      </div>
    </div>
  );
}
