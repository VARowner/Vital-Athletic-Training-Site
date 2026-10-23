/*
 * Contact + offer form handling for vitalathletic.com (static site on GitHub Pages).
 *
 * The forms were built by Weebly and used to post to Weebly's servers. This script takes them over:
 * it reads each field by its visible label, checks the required ones, and sends the answers to
 * Formspree, which emails them to the inbox the Formspree form is set up with and keeps a copy.
 *
 * To change where submissions go, change FORM_ENDPOINT below (Formspree → your form → Integration).
 * Until it is set, submitting opens a pre-filled email instead, so no inquiry is ever lost.
 */
(function () {
  "use strict";

  var FORM_ENDPOINT = ""; // e.g. "https://formspree.io/f/abcdwxyz"
  var FALLBACK_EMAIL = "mpitts@vitalathletic.com";

  var SUBJECTS = {
    "/contact.html": "Website: contact form",
    "/offer.html": "Website: free goal-setting session request",
  };

  function textOf(el) {
    return (el ? el.textContent : "").replace(/\*/g, "").replace(/\s+/g, " ").trim();
  }

  // Turns Weebly's field blocks into { "First name": "...", "My Goals Are": "Weight Loss, Muscle Tone" }.
  function collect(form) {
    var data = {};
    var missing = [];
    form.querySelectorAll(".wsite-form-field").forEach(function (field) {
      var labelEl = field.querySelector(".wsite-form-label");
      var label = textOf(labelEl).replace(/:$/, "");
      if (!label) return;
      var required = !!(labelEl && labelEl.querySelector(".form-required"));
      var value = "";

      var boxes = field.querySelectorAll("input[type=checkbox], input[type=radio]");
      if (boxes.length) {
        var picked = [];
        boxes.forEach(function (b) {
          if (b.checked) picked.push(textOf(field.querySelector('label[for="' + b.id + '"]')) || b.value);
        });
        value = picked.join(", ");
      } else {
        // Text inputs; a split name field has First/Last sub-labels.
        var parts = [];
        field.querySelectorAll("input:not([type=hidden]), textarea, select").forEach(function (inp) {
          if (inp.value && inp.value.trim()) parts.push(inp.value.trim());
        });
        value = parts.join(" ");
      }

      if (required && !value) missing.push(label);
      if (value) data[/e-?mail/i.test(label) && !boxes.length ? "email" : label] = value;
    });
    return { data: data, missing: missing };
  }

  function showMessage(form, html, isError) {
    var box = form.querySelector(".va-form-message");
    if (!box) {
      box = document.createElement("div");
      box.className = "va-form-message";
      box.style.cssText = "margin:12px 0;font-family:'Open Sans',sans-serif;font-size:15px;";
      form.appendChild(box);
    }
    box.style.color = isError ? "#c53030" : "#232323";
    box.innerHTML = html;
  }

  function mailtoFallback(subject, data) {
    var body = Object.keys(data).map(function (k) { return k + ": " + data[k]; }).join("\n");
    window.location.href =
      "mailto:" + FALLBACK_EMAIL + "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
  }

  function takeOver(original) {
    // Replacing the form with a clone drops every event handler Weebly attached to it.
    var form = original.cloneNode(true);
    original.parentNode.replaceChild(form, original);
    form.removeAttribute("action");
    form.querySelectorAll('input[type=hidden][name="ucfid"], input[name="recaptcha_token"], input[name="form_version"], input[name="wsite_approved"], input[name="wsite_subject"]')
      .forEach(function (n) { n.parentNode.removeChild(n); });

    // Spam trap: real people never see or fill this.
    var trap = document.createElement("input");
    trap.type = "text"; trap.name = "_gotcha"; trap.tabIndex = -1; trap.autocomplete = "off";
    trap.style.cssText = "position:absolute;left:-9999px;width:1px;height:1px;opacity:0";
    form.appendChild(trap);

    var subject = SUBJECTS[location.pathname] || "Website form";
    var sending = false;

    function submit(e) {
      if (e) {
        // Stop Weebly's own (document-level) handlers from also trying to send to its servers.
        e.preventDefault();
        e.stopPropagation();
        if (e.stopImmediatePropagation) e.stopImmediatePropagation();
      }
      if (sending) return;
      var res = collect(form);
      if (res.missing.length) {
        showMessage(form, "Please fill in: " + res.missing.join(", ") + ".", true);
        return;
      }
      if (res.data.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(res.data.email)) {
        showMessage(form, "Please enter a valid email address.", true);
        return;
      }
      if (trap.value) return; // a bot filled the trap; pretend nothing happened
      if (!FORM_ENDPOINT) { mailtoFallback(subject, res.data); return; }

      sending = true;
      showMessage(form, "Sending…", false);
      var payload = Object.assign({ _subject: subject, page: location.pathname }, res.data);
      fetch(FORM_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (r) {
          if (!r.ok) throw new Error("status " + r.status);
          var list = form.querySelector(".wsite-form-container");
          if (list) list.style.display = "none";
          form.querySelectorAll(".wsite-button, input[type=submit]").forEach(function (b) { b.style.display = "none"; });
          showMessage(form, "<strong>Thank you!</strong> We got your message and will be in touch soon.", false);
        })
        .catch(function () {
          sending = false;
          showMessage(
            form,
            'Sorry, that didn\'t send. Please try again, or email us at <a href="mailto:' + FALLBACK_EMAIL + '">' +
              FALLBACK_EMAIL + "</a>.",
            true
          );
        });
    }

    form.addEventListener("submit", submit);
    form.querySelectorAll(".wsite-button").forEach(function (btn) {
      btn.setAttribute("role", "button");
      btn.setAttribute("tabindex", "0");
      btn.style.cursor = "pointer";
      btn.addEventListener("click", submit);
      btn.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") submit(e); });
    });
  }

  function init() {
    document.querySelectorAll('form[id^="form-"]').forEach(takeOver);
  }

  // Run after Weebly's own scripts have attached their handlers, so the clone removes them.
  if (document.readyState === "complete") init();
  else window.addEventListener("load", init);
})();
