// mfdhome display client: shows the live SVG, patches changed groups, and
// sends acknowledgements (tap the banner or a tile) back over the WebSocket.
"use strict";

const body = document.body;
const screen = document.getElementById("screen");
const displayId = body.dataset.display;
const token = new URLSearchParams(location.search).get("token");
let socket = null;
let tiles = {}; // tile element id -> system id, for the page being shown
let previous = []; // serialized top-level children of the last frame received
let retryMs = 1000;
const serializer = new XMLSerializer();

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

// Replace only the top-level groups that changed, so animations keep their
// phase and nothing flickers. Frames are compared with the previous frame as
// received (same serializer on both sides); any structural change, or the
// first frame, swaps the whole SVG.
function patch(svgText) {
  const incoming = new DOMParser().parseFromString(svgText, "image/svg+xml").documentElement;
  const serialized = [...incoming.children].map((el) => serializer.serializeToString(el));
  const current = screen.querySelector("svg");
  const same =
    current &&
    previous.length === serialized.length &&
    current.children.length === incoming.children.length &&
    current.getAttribute("data-page") === incoming.getAttribute("data-page") &&
    current.getAttribute("data-theme") === incoming.getAttribute("data-theme") &&
    [...current.children].every((el, i) => el.id === incoming.children[i].id);
  if (same) {
    serialized.forEach((text, i) => {
      if (text !== previous[i]) current.children[i].replaceWith(document.importNode(incoming.children[i], true));
    });
  } else {
    screen.replaceChildren(document.importNode(incoming, true));
  }
  previous = serialized;
}

screen.addEventListener("click", (event) => {
  for (let el = event.target; el && el !== screen; el = el.parentElement) {
    if (el.id === "banner") return send({ type: "ack", target: "banner" });
    if (el.id in tiles) return send({ type: "ack", system: tiles[el.id] });
  }
});

function connect() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const query = token ? `?token=${encodeURIComponent(token)}` : "";
  socket = new WebSocket(`${scheme}://${location.host}/display/${displayId}/ws${query}`);
  socket.onopen = () => {
    retryMs = 1000;
    body.classList.remove("offline");
  };
  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "frame") {
      tiles = message.tiles;
      patch(message.svg);
    }
  };
  socket.onclose = () => {
    body.classList.add("offline");
    setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 30000);
  };
}

// Page selection for now: window.mfdSelect("electrical") (bezel buttons come later).
window.mfdSelect = (page) => send({ type: "select", page });

connect();
