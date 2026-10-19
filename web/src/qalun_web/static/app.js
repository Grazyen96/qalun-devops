// The page's only script: send the upload, then follow the job until its files are ready.
// The job's id goes in the address (#job=...), so a reload or a shared link picks it up again.

const form = document.getElementById("upload");
const formError = document.getElementById("form-error");
const surahSelect = form.elements.surah;
const surahField = document.getElementById("surah-field");
const jobSection = document.getElementById("job");
const jobTitle = document.getElementById("job-title");
const jobProgress = document.getElementById("job-progress");
const jobMessage = document.getElementById("job-message");
const jobFiles = document.getElementById("job-files");
const again = document.getElementById("again");

const POLL_MS = 2000;
const STAGES = {
  download: "Fetching the speech model",
  unpack: "Preparing the speech model",
  transcribe: "Listening to the recording",
  detect: "Finding the ayat",
  match: "Timing the ayat",
};
const FILE_LABELS = { srt: "Subtitles (SRT)", vtt: "Subtitles (WebVTT)", json: "Match data (JSON)" };

async function loadSurahs() {
  const response = await fetch("/api/surahs");
  if (!response.ok) return;
  for (const surah of await response.json()) {
    const option = document.createElement("option");
    option.value = surah.surah_num;
    option.textContent = `${surah.surah_num}. ${surah.name}`;
    option.dir = "auto";
    surahSelect.append(option);
  }
}

function showModeChoices() {
  // A lecture can quote any surah, so naming one only applies to a recitation.
  surahField.hidden = form.elements.mode.value !== "recitation";
}

async function errorText(response) {
  try {
    return (await response.json()).detail || `Error ${response.status}`;
  } catch {
    return `Error ${response.status}`;
  }
}

form.addEventListener("change", showModeChoices);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.hidden = true;
  if (!form.elements.file.files.length) {
    formError.textContent = "Choose a recording first.";
    formError.hidden = false;
    return;
  }
  const data = new FormData(form);
  if (data.get("mode") !== "recitation" || !data.get("surah")) data.delete("surah");

  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Uploading…";
  try {
    const response = await fetch("/api/jobs", { method: "POST", body: data });
    if (!response.ok) throw new Error(await errorText(response));
    const { id } = await response.json();
    location.hash = `job=${id}`;
    follow(id);
  } catch (error) {
    formError.textContent = error.message;
    formError.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Make subtitles";
  }
});

again.addEventListener("click", () => {
  history.replaceState(null, "", location.pathname);
  form.reset();
  showModeChoices();
  jobSection.hidden = true;
  form.hidden = false;
});

function render(job) {
  form.hidden = true;
  jobSection.hidden = false;
  jobTitle.textContent = job.filename;
  jobFiles.replaceChildren();
  again.hidden = job.status === "queued" || job.status === "running";
  jobProgress.hidden = !(job.status === "queued" || job.status === "running");

  if (job.status === "queued") {
    jobProgress.removeAttribute("value");
    jobMessage.textContent = "Waiting for a free worker…";
  } else if (job.status === "running") {
    if (job.fraction === null) jobProgress.removeAttribute("value");
    else jobProgress.value = job.fraction;
    jobMessage.textContent = STAGES[job.stage] || "Working…";
  } else if (job.status === "done") {
    jobMessage.textContent = "Done. The files are kept for a day.";
    for (const file of job.files) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = file.url;
      link.textContent = FILE_LABELS[file.name] || file.name;
      item.append(link);
      jobFiles.append(item);
    }
  } else {
    jobMessage.textContent = job.error || "Something went wrong.";
  }
}

async function follow(id) {
  const response = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
  if (response.status === 404) {
    render({ filename: "Job not found", status: "failed", error: await errorText(response), files: [] });
    return;
  }
  if (response.ok) {
    const job = await response.json();
    render(job);
    if (job.status === "done" || job.status === "failed") return;
  }
  setTimeout(() => follow(id), POLL_MS);
}

loadSurahs();
showModeChoices();
const resumed = new URLSearchParams(location.hash.slice(1)).get("job");
if (resumed) follow(resumed);
