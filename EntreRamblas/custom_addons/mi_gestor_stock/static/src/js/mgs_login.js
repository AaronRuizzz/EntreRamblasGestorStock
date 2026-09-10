// Páginas de acceso (login, primer acceso, recuperación): casilla «Mostrar la
// contraseña». Sin dependencias: se carga en web.assets_frontend, que no tiene
// el cargador de módulos de Odoo disponible siempre.
(function () {
    "use strict";
    function wire() {
        var boxes = document.querySelectorAll("[data-mgs-toggle-password]");
        for (var i = 0; i < boxes.length; i++) {
            (function (box) {
                var ids = (box.getAttribute("data-mgs-toggle-password") || "")
                    .split(",").map(function (s) { return s.trim(); }).filter(Boolean);
                box.addEventListener("change", function () {
                    for (var j = 0; j < ids.length; j++) {
                        var input = document.getElementById(ids[j]);
                        if (input) {
                            input.type = box.checked ? "text" : "password";
                        }
                    }
                });
            })(boxes[i]);
        }
    }
    if (document.readyState !== "loading") {
        wire();
    } else {
        document.addEventListener("DOMContentLoaded", wire);
    }
})();
