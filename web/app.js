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

const GRADE_LABEL = { A: "A 优", B: "B 合格", C: "C 差", U: "未分级" };

function shortId(id) {
  return id ? id.slice(0, 8) : "-";
}

function seamCell(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) {
    node.className = className;
  }
  return node;
}

async function refreshSeams(coil, limit) {
  const params = new URLSearchParams();
  if (coil) {
    params.set("coil", coil);
  }
  if (limit) {
    params.set("limit", limit);
  }
  const query = params.toString();
  const data = await loadJSON("/api/weld/seams" + (query ? "?" + query : ""));
  const list = document.getElementById("seamList");
  list.innerHTML = "";
  (data.seams || []).forEach(function (seam) {
    const tr = document.createElement("tr");
    tr.appendChild(seamCell("td", GRADE_LABEL[seam.grade] || seam.grade, "grade grade-" + seam.grade));
    tr.appendChild(seamCell("td", seam.coil_id || "-"));
    tr.appendChild(seamCell("td", fmt(seam.position, 1)));
    tr.appendChild(seamCell("td", seam.voltage ? fmt(seam.voltage, 1) : "-"));
    tr.appendChild(seamCell("td", seam.current ? fmt(seam.current, 0) : "-"));
    tr.appendChild(seamCell("td", seam.line_speed ? fmt(seam.line_speed, 2) : "-"));
    tr.appendChild(seamCell("td", seam.heat_input ? fmt(seam.heat_input, 0) : "-"));
    tr.appendChild(seamCell("td", seam.grade === "U" ? "-" : (seam.deviation * 100).toFixed(1) + "%"));
    tr.appendChild(seamCell("td", seam.source === "manual" ? "补录" : "在线"));
    tr.appendChild(seamCell("td", seam.at ? new Date(seam.at).toLocaleString() : "-"));
    const repairs = seamCell("td", "…", "repair-pending");
    tr.appendChild(repairs);
    const detail = seamCell("td", "");
    const fill = document.createElement("button");
    fill.type = "button";
    fill.textContent = "返修";
    fill.addEventListener("click", function () {
      const form = document.querySelector('form[data-form="seam-repair"]');
      form.id.value = seam.seam_id;
      form.reason.focus();
    });
    detail.appendChild(fill);
    tr.appendChild(detail);
    list.appendChild(tr);
    loadJSON("/api/weld/seam?id=" + seam.seam_id).then(function (d) {
      const n = (d.repairs || []).length;
      repairs.textContent = n ? n + " 次" : "-";
      repairs.className = n ? "repair-count" : "";
    }).catch(function () {
      repairs.textContent = "?";
    });
  });
  const repairData = await loadJSON("/api/weld/repairs" + (coil ? "?coil=" + encodeURIComponent(coil) : ""));
  const repairList = document.getElementById("repairList");
  repairList.innerHTML = "";
  (repairData.repairs || []).forEach(function (repair) {
    const tr = document.createElement("tr");
    tr.appendChild(seamCell("td", repair.at ? new Date(repair.at).toLocaleString() : "-"));
    tr.appendChild(seamCell("td", repair.coil_id || "-"));
    tr.appendChild(seamCell("td", shortId(repair.seam_id)));
    tr.appendChild(seamCell("td", repair.reason || "-"));
    tr.appendChild(seamCell("td", repair.operator || "-"));
    tr.appendChild(seamCell("td", repair.note || "-"));
    repairList.appendChild(tr);
  });
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
  "seam-reload": async () => {
    const form = document.querySelector('form[data-form="seam-query"]');
    await refreshSeams(form.coil.value, form.limit.value);
  },
};

const FORM_CALLS = {
  "weld-power": (form) => post("/api/weld/power", readForm(form)),
  "weld-splice": (form) => post("/api/weld/splice", readForm(form)),
  "heat-target": async (form) => {
    await post("/api/weld/heat-target", readForm(form));
    const query = document.querySelector('form[data-form="seam-query"]');
    await refreshSeams(query.coil.value, query.limit.value);
  },
  "seam-query": (form) => refreshSeams(form.coil.value, form.limit.value),
  "seam-repair": async (form) => {
    await post("/api/weld/repair", readForm(form));
    form.reset();
    const query = document.querySelector('form[data-form="seam-query"]');
    await refreshSeams(query.coil.value, query.limit.value);
  },
  "seam-manual": async (form) => {
    const data = readForm(form);
    Object.keys(data).forEach(function (key) {
      if (data[key] === "") {
        delete data[key];
      }
    });
    await post("/api/weld/seam/manual", data);
    form.reset();
    const query = document.querySelector('form[data-form="seam-query"]');
    await refreshSeams(query.coil.value, query.limit.value);
  },
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
    if (button.dataset.tab === "seams") {
      const form = document.querySelector('form[data-form="seam-query"]');
      refreshSeams(form.coil.value, form.limit.value).catch(function (error) {
        console.error(error);
      });
    }
  });
});

refresh();
setInterval(refresh, 3000);
