let sync_ring = document.querySelector(".sync-ring > sl-progress-ring")
let sync_button = document.querySelector(".sync-settings > sl-button")
let turbo = false;

function sync() {
  config = get_config();
  fetch("/sync-settings", {
    method: "POST",
    body: JSON.stringify(config),
    headers: {
      "Content-Type": "application/json",

    }
  }).then(e => {
    console.log(e)
    if (e.ok) {
      e.json().then(data => {
        if (data["message"] != "OK") {
          notify(data["message"], "danger", "exclamation-octagon")
        } else {
          notify("Sync started!")
          set_turbo()
        }
      })
    } else {
      notify("There was an error starting sync.", "danger", "exclamation-octagon")
    }
  })
}

function set_turbo() {
  sync_ring.value = 0;
  sync_ring.innerHTML = "0%";
  sync_button.disabled = true;
  set_checkbox(true)
  turbo = true;
  set_sync_progress()
  var timer = setInterval(() => {
    if (sync_ring.value != 100) {
      set_sync_progress()
    } else {
      clearInterval(timer)
      sync_button.disabled = false;
      set_checkbox(false)
      turbo = false
    }
  }, 1000)
}

function set_checkbox(disabled){
  let types_array = document.querySelectorAll("#test-types > sl-checkbox")
  let patterns_array = document.querySelectorAll("#test-patterns > sl-checkbox")
  types_array.forEach(element => {
    element.disabled = disabled
  })
  patterns_array.forEach(element => {
    element.disabled = disabled
  })
}
function get_config() {
  let types_array = document.querySelectorAll("#test-types > sl-checkbox")
  let types = [];
  types_array.forEach(element => {
    if (element.checked) {
      types.push(element.getAttribute("name"))
    }
  });

  let patterns_array = document.querySelectorAll("#test-patterns > sl-checkbox")
  let patterns = [];
  patterns_array.forEach(element => {
    if (element.checked) {
      patterns.push(element.getAttribute("name"))
    }
  });

  return { config: { tests: types, patterns: patterns } };
}

function set_config(config) {
  let types = config["config"]["tests"]
  let patterns = config["config"]["patterns"]

  types.forEach(element => {
    document.querySelector(`sl-checkbox[name=${element}]`).checked = true;
  });

  patterns.forEach(element => {
    document.querySelector(`sl-checkbox[name=${element}]`).checked = true;
  });

}

function get_status() {
  fetch("/status").then(r => {
    r.json().then(data => {
      set_config(data)
      sync_ring.value = data["progress"]
      sync_ring.innerHTML = data["progress"] + "%"

      if (data["sync"] && !turbo) {
        set_turbo()
      }
    })
  })
}

function set_sync_progress() {
  fetch("/sync").then(e => {
    if (e.ok) {
      e.text().then(prog => {
        sync_ring.value = prog
        sync_ring.innerHTML = prog + "%"
      })
    }
  })
}

get_status()
setInterval(get_status, 20000);


