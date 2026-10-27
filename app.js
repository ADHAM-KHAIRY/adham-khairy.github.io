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

    /* ---- Copy button on code blocks -------------------------- */
    function initCodeCopy() {
        document.querySelectorAll('.code-copy').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const pre = btn.closest('.code-block').querySelector('pre');
                if (!pre) return;

                const done = function () {
                    btn.textContent = 'copied';
                    btn.classList.add('done');
                    setTimeout(function () {
                        btn.textContent = 'copy';
                        btn.classList.remove('done');
                    }, 1600);
                };

                if (navigator.clipboard) {
                    navigator.clipboard.writeText(pre.innerText).then(done, function () {
                        btn.textContent = 'failed';
                    });
                    return;
                }
                // older browsers, and any page not served over https
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(pre);
                sel.removeAllRanges();
                sel.addRange(range);
                try { document.execCommand('copy'); done(); } catch (e) { btn.textContent = 'failed'; }
                sel.removeAllRanges();
            });
        });
    }

    /* ---- HackerOne badge ------------------------------------- */
    /* HackerOne has no embeddable badge, so the figures are snapshotted
       into data/hackerone.json by CI and rendered here. */
    function initHackerOneBadge() {
        const el = document.getElementById('h1-badge');
        if (!el) return;

        fetch('data/hackerone.json', { cache: 'no-cache' })
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (d) {
                const figs = [
                    ['rep', d.reputation],
                    ['rank', d.rank ? '#' + d.rank : null],
                    ['signal', d.signal],
                    ['impact', d.impact]
                ].filter(function (f) { return f[1] !== null && f[1] !== undefined; });

                el.href = d.profile_url || el.href;
                el.innerHTML =
                    (d.avatar ? '<img src="' + d.avatar + '" alt="" loading="lazy">' : '') +
                    '<div class="who">' +
                        '<div class="plat">HackerOne</div>' +
                        '<div class="handle">@' + d.username + '</div>' +
                    '</div>' +
                    '<div class="figs">' + figs.map(function (f) {
                        return '<div class="fig"><b>' + f[1] + '</b><span>' + f[0] + '</span></div>';
                    }).join('') + '</div>';
                el.hidden = false;
            })
            .catch(function (err) {
                console.warn('[h1-badge] unavailable:', err);
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        initTyping();
        initObservers();
        initConsole();
        initHackerOneBadge();
        initCodeCopy();
    });
})();
