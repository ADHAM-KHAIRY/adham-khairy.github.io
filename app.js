/* ============================================================
   0xSponge — shared interactions
   ============================================================ */
(function () {
    'use strict';

    /* ---- Hero typing effect ---------------------------------- */
    function initTyping() {
        const el = document.querySelector('[data-type]');
        if (!el) return;
        let words;
        try { words = JSON.parse(el.getAttribute('data-type')); }
        catch (e) { return; }
        if (!Array.isArray(words) || !words.length) return;

        let wi = 0, ci = 0, deleting = false;
        function tick() {
            const word = words[wi];
            el.textContent = word.substring(0, ci);
            if (!deleting) {
                if (ci < word.length) { ci++; return setTimeout(tick, 90); }
                deleting = true;
                return setTimeout(tick, 1400);
            }
            if (ci > 0) { ci--; return setTimeout(tick, 45); }
            deleting = false;
            wi = (wi + 1) % words.length;
            setTimeout(tick, 350);
        }
        tick();
    }

    /* ---- Count-up stats -------------------------------------- */
    function animateCount(el) {
        const target = parseInt(el.getAttribute('data-count'), 10) || 0;
        const suffix = el.getAttribute('data-suffix') || '';
        const dur = 1400;
        let start = null;
        function step(ts) {
            if (start === null) start = ts;
            const p = Math.min((ts - start) / dur, 1);
            const eased = 1 - Math.pow(1 - p, 3);
            el.textContent = Math.floor(eased * target) + suffix;
            if (p < 1) requestAnimationFrame(step);
            else el.textContent = target + suffix;
        }
        requestAnimationFrame(step);
    }

    /* ---- Scroll reveal + trigger counters -------------------- */
    function initObservers() {
        const revealEls = document.querySelectorAll('.reveal');
        const counters = document.querySelectorAll('[data-count]');

        if (!('IntersectionObserver' in window)) {
            revealEls.forEach(function (e) { e.classList.add('in'); });
            counters.forEach(animateCount);
            return;
        }

        const revObs = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) { en.target.classList.add('in'); revObs.unobserve(en.target); }
            });
        }, { threshold: 0.12 });
        revealEls.forEach(function (e) { revObs.observe(e); });

        const cntObs = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) { animateCount(en.target); cntObs.unobserve(en.target); }
            });
        }, { threshold: 0.5 });
        counters.forEach(function (e) { cntObs.observe(e); });
    }

    /* ---- Contact console typewriter -------------------------- */
    function initConsole() {
        const el = document.querySelector('[data-console]');
        if (!el) return;
        const html = el.innerHTML;
        el.innerHTML = '';
        let i = 0;
        (function type() {
            if (i >= html.length) return;
            // skip whole tags in one step so markup renders cleanly
            if (html[i] === '<') {
                const close = html.indexOf('>', i);
                el.innerHTML += html.substring(i, close + 1);
                i = close + 1;
            } else {
                el.innerHTML += html[i];
                i++;
            }
            setTimeout(type, 12);
        })();
    }

    document.addEventListener('DOMContentLoaded', function () {
        initTyping();
        initObservers();
        initConsole();
    });
})();
