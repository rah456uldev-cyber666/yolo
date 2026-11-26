// Disable the "Resend code" button until the cooldown has passed.
(function () {
  var btn = document.getElementById("resend");
  if (!btn) return;
  var wait = parseInt(btn.dataset.wait || "0", 10);
  var label = btn.textContent;
  function tick() {
    if (wait > 0) {
      btn.disabled = true;
      btn.textContent = label + " in " + wait + "s";
      wait -= 1;
      setTimeout(tick, 1000);
    } else {
      btn.disabled = false;
      btn.textContent = label;
    }
  }
  tick();
})();
