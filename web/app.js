const LAMP_SOURCES = [
  ["对中确认", (s) => s.aligned],
  ["张力已落盘", (s) => s.tension && s.tension.allowed],
  ["酸泵运行", (s) => s.pump && s.pump.running],
  ["喷淋开启", (s) => s.pickle && s.pickle.rinsing],
  ["排风建立", (s) => s.exit && s.exit.exhaust],
  ["烘干升温", (s) => s.dry && s.dry.heating],
  ["焊接联锁释放", (s) => s.weld && s.weld.interlock],
  ["带尾已冲净", (s) => s.strip && !s.strip.tailDirty],
];

function fmt(value, digits) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return value.toFixed(digits === undefined ? 1 : digits);
  }
  return String(value);
}

async function loadJSON(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!data.ok) {
    const detail = data.detail && data.detail.detail ? data.detail.detail : data.error;
    throw new Error(detail || "request failed");
  }
  return data;
}

function post(path, params) {
  const query = params ? "?" + new URLSearchParams(params).toString() : "";
  return loadJSON(path + query, { method: "POST", headers: { Accept: "application/json" } });
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function renderState(state) {
  const badge = document.getElementById("phase");
  badge.textContent = state.phase || "idle";
  badge.className = "badge " + (state.phase === "fault" ? "fault" : "running");
  setText("coil", state.coil || "-");
  setText("head", fmt(state.head, 1));
  setText("aligned", state.aligned ? "已确认" : "未确认");
  setText("track", fmt(state.strip ? state.strip.track : 0, 1));
  setText("tension", fmt(state.tension ? state.tension.setpoint : 0, 1));
  setText("effective", fmt(state.tension ? state.tension.effective : 0, 1));
  setText("concentration", fmt(state.pickle ? state.pickle.concentration : 0, 2));
  setText("level", fmt(state.pickle ? state.pickle.level : 0, 2));
  setText("rinsing", state.pickle && state.pickle.rinsing ? "开" : "关");
  setText("pump", state.pump && state.pump.running ? "运行" : "停");
  setText("dry", state.dry && state.dry.heating ? "升温" : "停");
  setText("tail", state.strip && state.strip.tailDirty ? "脏" : "净");
  setText("speed", fmt(state.strip ? state.strip.speed : 0, 2));
  setText("travel", fmt(state.strip ? state.strip.travel : 0, 1));

  const weld = state.weld || {};
  const gradeText = weld.seam
    ? shortSeam(weld.seam) + " / " + (weld.lastGrade || "-") +
      "（" + (GRADE_REASONS[weld.lastGradeReason] || "无判定") + "）"
    : "无焊缝";
  setText("seamGrade", gradeText);

  const lamps = document.getElementById("lamps");
  lamps.innerHTML = "";
  LAMP_SOURCES.forEach(function (entry) {
    const li = document.createElement("li");
    const on = Boolean(entry[1](state));
    li.className = "lamp " + (on ? "on" : "off");
    li.textContent = entry[0];
    lamps.appendChild(li);
  });

  const alarms = document.getElementById("alarmList");
  alarms.innerHTML = "";
  const active = state.alarms || [];
  if (!active.length) {
    const li = document.createElement("li");
    li.className = "clear";
    li.textContent = "无活动告警";
    alarms.appendChild(li);
  } else {
    active.forEach(function (id) {
      const li = document.createElement("li");
      li.textContent = id;
      alarms.appendChild(li);
    });
  }
}

function renderEvents(events) {
  const list = document.getElementById("auditList");
  list.innerHTML = "";
  events.slice(-40).reverse().forEach(function (event) {
    const li = document.createElement("li");
    const when = event.at ? new Date(event.at).toLocaleTimeString() : "";
    li.textContent = when + " [" + event.kind + "] " + (event.message || "");
    list.appendChild(li);
  });
}

function renderSummary(summary) {
  const list = document.getElementById("summary");
  list.innerHTML = "";
  Object.keys(summary).sort().forEach(function (kind) {
    const li = document.createElement("li");
    li.textContent = kind + " x " + summary[kind];
    list.appendChild(li);
  });
}

function renderSequence(sequence) {
  const list = document.getElementById("sequenceList");
  list.innerHTML = "";
  if (!sequence) {
    return;
  }
  const head = document.createElement("li");
  head.textContent = "流程 " + (sequence.label || "-");
  list.appendChild(head);
  (sequence.steps || []).forEach(function (step) {
    const li = document.createElement("li");
    li.className = step.ok ? "step-ok" : "step-bad";
    li.textContent = (step.ok ? "通过 " : "失败 ") + step.name + (step.detail ? " :: " + step.detail : "");
    list.appendChild(li);
  });
}

const GRADE_REASONS = {
  "in-band": "线能量在工艺窗口内",
  "heat-high": "线能量偏高",
  "heat-low": "线能量偏低",
  "speed-missing": "缺少有效焊速",
  "power-missing": "缺少焊接功率",
};

function shortSeam(id) {
  return id ? id.slice(0, 8) : "-";
}

function fmtTime(iso) {
  return iso ? new Date(iso).toLocaleString() : "-";
}

let seamFilter = {};

function renderSeams(seams) {
  const body = document.getElementById("seamList");
  body.innerHTML = "";
  if (!seams.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="11" class="muted">没有焊缝记录</td>';
    body.appendChild(tr);
    return;
  }
  seams.forEach(function (seam) {
    const tr = document.createElement("tr");
    const repairs = seam.repairs || [];
    const repairText = repairs.length
      ? repairs.map(function (r) {
          return fmtTime(r.at) + " " + (r.note || "");
        }).join("；")
      : "无";
    tr.innerHTML =
      "<td>" + fmtTime(seam.at) + "</td>" +
      "<td title=\"" + seam.seam_id + "\">" + shortSeam(seam.seam_id) + "</td>" +
      "<td>" + (seam.coil_id || "-") + "</td>" +
      "<td>" + fmt(seam.position, 1) + "</td>" +
      "<td>" + fmt(seam.voltage, 1) + "</td>" +
      "<td>" + fmt(seam.current, 0) + "</td>" +
      "<td>" + fmt(seam.weld_speed, 2) + "</td>" +
      "<td>" + fmt(seam.heat_input, 0) + "</td>" +
      "<td><span class=\"grade grade-" + (seam.grade || "-").toLowerCase() + "\">" +
        (seam.grade || "-") +
        "<br><small>" + (GRADE_REASONS[seam.grade_reason] || "") + "</small></span></td>" +
      "<td>" + repairText + "</td>" +
      "<td></td>";
    const button = document.createElement("button");
    button.textContent = "登记返修";
    button.addEventListener("click", function () {
      const form = document.querySelector('form[data-form="seam-repair"]');
      form.seam.value = seam.seam_id;
      form.note.focus();
    });
    tr.lastElementChild.appendChild(button);
    body.appendChild(tr);
  });
}

async function querySeams(params) {
  seamFilter = params || {};
  const query = new URLSearchParams(seamFilter).toString();
  const data = await loadJSON("/api/weld/seams" + (query ? "?" + query : ""));
  renderSeams(data.seams || []);
}

async function refresh() {
  try {
    const data = await loadJSON("/api/state");
    renderState(data.state || {});
    renderSequence(data.state ? data.state.sequence : null);
    const summary = await loadJSON("/api/audit/summary");
    renderSummary(summary.summary || {});
  } catch (error) {
    console.error(error);
  }
}

async function refreshAudit(kind, limit) {
  const params = {};
  if (kind) {
    params.kind = kind;
  }
  if (limit) {
    params.limit = limit;
  }
  const query = new URLSearchParams(params).toString();
  const data = await loadJSON("/api/audit" + (query ? "?" + query : ""));
  renderEvents(data.events || []);
}

const OP_CALLS = {
  "weld-confirm": () => post("/api/weld/confirm"),
  "weld-alarm": () => post("/api/weld/alarm"),
  "weld-clear": () => post("/api/weld/clear"),
  "weld-release": () => post("/api/weld/release"),
  "dry-heat": () => post("/api/dry/heat"),
  "dry-reheat": () => post("/api/dry/reheat"),
  "entry-correct": () => post("/api/entry/correct"),
  "stop": () => post("/api/stop"),
  "strip-sag": async () => {
    const data = await loadJSON("/api/strip/sag");
    window.alert("垂度 " + fmt(data.sag, 2) + " mm");
  },
};

const FORM_CALLS = {
  "weld-power": (form) => post("/api/weld/power", readForm(form)),
  "weld-splice": (form) => post("/api/weld/splice", readForm(form)),
  "tension-ramp": (form) => post("/api/tension/ramp", readForm(form)),
  "tension-calibrate": (form) => post("/api/tension/calibrate", readForm(form)),
  "pump-start": (form) => post("/api/pump/start", readForm(form)),
  "pump-replenish": (form) => post("/api/pump/replenish", readForm(form)),
  "pickle-calibrate": (form) => post("/api/pickle/calibrate", readForm(form)),
  "dry-dew": (form) => post("/api/dry/dew", readForm(form)),
  "dry-heat-target": (form) => post("/api/dry/heat-target", readForm(form)),
  "strip-advance": (form) => post("/api/strip/advance", readForm(form)),
  "strip-speed": (form) => post("/api/strip/speed", readForm(form)),
  "entry-offset": (form) => post("/api/entry/offset", readForm(form)),
  "entry-sample": (form) => post("/api/entry/sample", readForm(form)),
  "shear-offset": (form) => post("/api/exit/shear-offset", readForm(form)),
  "exit-weight": (form) => post("/api/exit/weight", readForm(form)),
  "cycle": (form) => post("/api/cycle", readForm(form)),
  "audit-query": (form) => refreshAudit(form.kind.value, form.limit.value),
  "seam-query": (form) => {
    const params = {};
    if (form.coil.value.trim()) {
      params.coil = form.coil.value.trim();
    }
    if (form.limit.value) {
      params.limit = form.limit.value;
    }
    return querySeams(params);
  },
  "seam-repair": async (form) => {
    await post("/api/weld/repair", readForm(form));
    form.note.value = "";
    await querySeams(seamFilter);
  },
};

function readForm(form) {
  const data = {};
  new FormData(form).forEach(function (value, key) {
    data[key] = value;
  });
  return data;
}

document.querySelectorAll("button[data-op]").forEach(function (button) {
  button.addEventListener("click", async function () {
    const call = OP_CALLS[button.dataset.op];
    if (!call) {
      return;
    }
    try {
      await call();
      await refresh();
    } catch (error) {
      window.alert(error.message);
    }
  });
});

document.querySelectorAll("form[data-form]").forEach(function (form) {
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const call = FORM_CALLS[form.dataset.form];
    if (!call) {
      return;
    }
    try {
      await call(form);
      await refresh();
    } catch (error) {
      window.alert(error.message);
    }
  });
});

document.querySelectorAll("button.tab").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".tabpage").forEach(function (page) {
      page.classList.add("hidden");
    });
    const target = document.getElementById("tab-" + button.dataset.tab);
    if (target) {
      target.classList.remove("hidden");
    }
  });
});

refresh();
querySeams({ limit: 50 }).catch(console.error);
setInterval(refresh, 3000);
