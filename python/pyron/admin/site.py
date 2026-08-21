"""Django-shaped admin site: register models, operate them from /admin."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from starlette.requests import Request
from starlette.staticfiles import StaticFiles

from pyron.admin import auth, inspect as insp
from pyron.admin.options import ModelAdmin, TabularInline
from pyron.admin.i18n import (
    LANG_COOKIE,
    LOCALES,
    LOCALE_LABELS,
    THEME_COOKIE,
    THEMES,
    Translator,
    resolve_locale,
    resolve_theme,
)
from pyron.exceptions import HTTPException
from pyron.responses import RedirectResponse, Response
from pyron.templates import Templates

PKG = Path(__file__).resolve().parent
TEMPLATES_DIR = PKG / "templates"
ASSETS_DIR = PKG / "static"


class _Bound:
    def __init__(self, model: type, admin: ModelAdmin, store: Any = None, kind: str = "sql") -> None:
        self.model = model
        self.admin = admin
        self.store = store
        self.kind = kind
        self.slug = (getattr(admin, "slug", None) or insp.slug_for(model)).strip() or insp.slug_for(model)
        self.pk = insp.primary_key(model)
        singular = admin.verbose_name or model.__name__
        self.name = singular
        self.plural = admin.verbose_name_plural or (singular + "s")
        self.fields = insp.field_specs(model, exclude=admin.exclude)
        display = admin.list_display
        if not display:
            display = [f["name"] for f in self.fields[:6]]
        self.list_display = display


class AdminSite:
    """The desk. Mount it on a Pyron app and register SQLModel tables."""

    def __init__(
        self,
        engine: Any | None = None,
        *,
        title: str | None = None,
        secret: bytes | None = None,
        mongo: Any | None = None,
        pages: bool = True,
    ) -> None:
        self.engine = engine
        self.title = title
        self.secret = secret or auth.load_secret()
        self._bound: dict[str, _Bound] = {}
        self._order: list[str] = []
        self.prefix = "/admin"
        self.app: Any = None
        self.templates = Templates(TEMPLATES_DIR)
        self._user_model = None
        self._sql_store: Any = None
        self._doc_store: Any = None
        self.pages_enabled = pages
        self._page_templates: Templates | None = None
        if engine is not None:
            from pyron.store import SqlStore

            self._sql_store = SqlStore(engine)
        if mongo is not None:
            self.bind_mongo(mongo)

    def _store_for(self, model: type) -> tuple[Any, str]:
        from pyron.store import is_document

        if is_document(model):
            if self._doc_store is None:
                raise RuntimeError(
                    f"{model.__name__} is a Document. Pass admin_mongo=... or set MONGO_URL."
                )
            return self._doc_store, getattr(self._doc_store, "kind", "mongo")
        if self._sql_store is None:
            if self.engine is None:
                self.ensure_tables()
            from pyron.store import SqlStore

            self._sql_store = SqlStore(self.engine)
        return self._sql_store, "sql"

    def register(
        self,
        model: type,
        admin: type[ModelAdmin] | ModelAdmin | None = None,
        *,
        first: bool = False,
        sync: bool = True,
    ) -> None:
        if admin is None:
            opts = ModelAdmin(model)
        elif isinstance(admin, type):
            opts = admin()
            opts.model = model
        else:
            opts = admin
            opts.model = model
        store, kind = self._store_for(model)
        bound = _Bound(model, opts, store=store, kind=kind)
        existed = bound.slug in self._bound
        self._bound[bound.slug] = bound
        if not existed:
            if first:
                self._order.insert(0, bound.slug)
            else:
                self._order.append(bound.slug)
        if sync and self.engine is not None:
            self._sync_permissions()

    def bind(self, engine: Any) -> None:
        from pyron.store import SqlStore

        self.engine = engine
        self._sql_store = SqlStore(engine)
        for bound in self.models():
            if bound.kind == "sql":
                bound.store = self._sql_store
        self.ensure_tables()

    def bind_mongo(self, mongo: Any) -> None:
        if mongo is None:
            self._doc_store = None
            return
        if hasattr(mongo, "list") and hasattr(mongo, "insert"):
            self._doc_store = mongo
        else:
            from pyron.mongo import MongoStore

            self._doc_store = MongoStore(mongo)
        for bound in self.models():
            from pyron.store import is_document

            if is_document(bound.model):
                bound.store = self._doc_store
                bound.kind = getattr(self._doc_store, "kind", "mongo")

    def models(self) -> list[_Bound]:
        return [self._bound[s] for s in self._order]

    def get(self, slug: str) -> _Bound:
        bound = self._bound.get(slug)
        if bound is None:
            raise HTTPException(404, "That table is not on the admin panel.")
        return bound

    def user_model(self):
        if self._user_model is None:
            self._user_model = auth.user_model()
        return self._user_model

    def ensure_tables(self) -> None:
        if self.engine is None:
            from pyron.db import create_engine

            self.engine = create_engine()
        if self._sql_store is None:
            from pyron.store import SqlStore

            self._sql_store = SqlStore(self.engine)
        from sqlmodel import SQLModel

        for cls in auth.auth_table_classes():
            SQLModel.metadata.create_all(self.engine, tables=[cls.__table__])
        from pyron.siteconfig import SiteSettings, seed_site

        SQLModel.metadata.create_all(self.engine, tables=[SiteSettings.__table__])
        seed_site(self.engine, title=self.title or (self.app.title if self.app else "Pyron"))
        for bound in self.models():
            table = getattr(bound.model, "__table__", None)
            if table is not None:
                SQLModel.metadata.create_all(self.engine, tables=[table])
            for spec in bound.admin.inlines or []:
                inline = spec() if isinstance(spec, type) else spec
                child = getattr(inline, "model", None)
                child_table = getattr(child, "__table__", None) if child is not None else None
                if child_table is not None:
                    SQLModel.metadata.create_all(self.engine, tables=[child_table])
        self._sync_permissions()

    def _sync_permissions(self) -> None:
        if self.engine is None:
            return
        with self.session() as db:
            staff = auth.ensure_staff_group(db)
            for bound in self.models():
                for action in auth.ALL_ACTIONS:
                    perm = auth.ensure_permission(
                        db, f"{bound.slug}.{action}", f"{action} {bound.name}"
                    )
                    if action in auth.STAFF_ACTIONS:
                        auth.grant_group_permission(db, staff, perm)
            db.commit()

    def visible_models(self, user: Any) -> list[_Bound]:
        if user is None:
            return []
        return [b for b in self.models() if user.has_perm(f"{b.slug}.view")]

    def _require_perm(self, user: Any, slug: str, action: str) -> None:
        from pyron.authz import PermissionDenied

        code = f"{slug}.{action}"
        if not getattr(user, "has_perm", lambda _c: False)(code):
            raise PermissionDenied(code)

    def render_denied(self, request: Request, permission: str, status: int = 403) -> Response:
        sess = auth.read_session(request, self.secret)
        user = self._user_from_session(sess)
        t = self._t(request)
        return self._render(
            request,
            "forbidden.html",
            {
                "nav": "desk",
                "permission": permission,
                "message": t("need_permission", permission=permission),
                "next_step": t("need_permission_next"),
            },
            status=status,
            session=sess or {},
            user=user,
        )

    def engine_label(self) -> str:
        bits = []
        if self.engine is not None:
            try:
                bits.append(str(self.engine.url))
            except Exception:
                bits.append("sql")
        if self._doc_store is not None:
            bits.append(getattr(self._doc_store, "kind", "mongo"))
        return " · ".join(bits) if bits else "not bound"

    def session(self):
        from sqlmodel import Session

        if self.engine is None:
            self.ensure_tables()
        return Session(self.engine)

    def attach(self, app: Any, prefix: str = "/admin") -> None:
        self.app = app
        self.prefix = prefix.rstrip("/") or "/admin"
        app.admin = self
        if self.pages_enabled:
            self.install_pages()
        app.mount(f"{self.prefix}/assets", _AdminAssets(), name="admin-assets")
        routes: list[tuple[str, Callable, list[str]]] = [
            ("/setup", self.setup_view, ["GET", "POST"]),
            ("/login", self.login_view, ["GET", "POST"]),
            ("/logout", self.logout_view, ["POST", "GET"]),
            ("/prefs", self.prefs_view, ["GET"]),
            ("/", self.desk_view, ["GET"]),
            ("/settings", self.settings_view, ["GET", "POST"]),
            ("/preview-markdown", self.preview_markdown, ["POST"]),
            ("/routes", self.routes_view, ["GET"]),
            ("/users", self.users_list, ["GET"]),
            ("/users/new", self.user_new, ["GET", "POST"]),
            ("/users/{user_id}", self.user_edit, ["GET", "POST"]),
            ("/m/{slug}", self.model_list, ["GET"]),
            ("/m/{slug}/action", self.model_action, ["POST"]),
            ("/m/{slug}/action/confirm", self.model_action_confirm, ["GET", "POST"]),
            ("/m/{slug}/new", self.model_new, ["GET", "POST"]),
            ("/m/{slug}/{pk}", self.model_edit, ["GET", "POST"]),
            ("/m/{slug}/{pk}/delete", self.model_delete, ["GET", "POST"]),
        ]
        for path, handler, methods in routes:
            app.add_api_route(
                self.prefix + path,
                handler,
                methods=methods,
                include_in_schema=False,
                name=f"admin_{handler.__name__}",
            )
        if self.engine is not None:
            self.ensure_tables()
            if self.pages_enabled:
                self._seed_pages()

    def install_pages(self) -> None:
        from pyron.pages import Page, make_page_admin

        if "pages" not in self._bound:
            self.register(Page, make_page_admin(), first=True, sync=False)
        self._bind_page_templates()
        if self.app is None:
            return
        self.app.add_api_route(
            "/p",
            self.public_pages_index,
            methods=["GET"],
            include_in_schema=False,
            name="public_pages_index",
        )
        self.app.add_api_route(
            "/p/{slug}",
            self.public_page_view,
            methods=["GET"],
            include_in_schema=False,
            name="public_page",
        )

    def _bind_page_templates(self) -> None:
        from pyron.pages import TEMPLATES_DIR

        app = self.app
        if app is not None and getattr(app, "templates", None) is not None:
            app.templates.add_search_path(TEMPLATES_DIR)
            return
        if self._page_templates is None:
            self._page_templates = Templates(TEMPLATES_DIR)

    def _public_templates(self) -> Templates:
        self._bind_page_templates()
        app = self.app
        if app is not None and getattr(app, "templates", None) is not None:
            return app.templates
        if self._page_templates is None:
            from pyron.pages import TEMPLATES_DIR

            self._page_templates = Templates(TEMPLATES_DIR)
        return self._page_templates

    def _seed_pages(self) -> None:
        from pyron.pages import seed_pages

        title = self.title or (self.app.title if self.app else "Pyron")
        seed_pages(self.engine, title=title)

    def _resolve_page_template(self, templates: Templates, name: str) -> str:
        try:
            templates.get_template(name)
            return name
        except Exception:
            return name

    async def public_pages_index(self, request: Request):
        self.ensure_tables()
        self._seed_pages()
        from pyron.pages import published_pages

        pages = published_pages(self.engine)
        templates = self._public_templates()
        return await templates.render(
            request,
            self._resolve_page_template(templates, "pages.html"),
            {
                "pages": pages,
                "desk_title": self.title or (self.app.title if self.app else "Pyron"),
            },
        )

    async def public_page_view(self, request: Request, slug: str):
        self.ensure_tables()
        self._seed_pages()
        from pyron.pages import load_page

        row = load_page(self.engine, slug)
        if row is None:
            raise HTTPException(404, "That page is not here.")
        if not row.published:
            sess = auth.read_session(request, self.secret)
            user = self._user_from_session(sess) if sess else None
            if user is None:
                raise HTTPException(404, "That page is not here.")
        templates = self._public_templates()
        return await templates.render(
            request,
            self._resolve_page_template(templates, "page.html"),
            {
                "page": row,
                "desk_title": self.title or (self.app.title if self.app else "Pyron"),
            },
        )

    # ------------------------------------------------------------------
    # Render + auth
    # ------------------------------------------------------------------

    def url(self, path: str = "") -> str:
        if not path:
            return self.prefix + "/"
        if not path.startswith("/"):
            path = "/" + path
        return self.prefix + path

    def _render(
        self,
        request: Request,
        name: str,
        context: dict[str, Any],
        *,
        status: int = 200,
        session: dict[str, Any] | None = None,
        user: Any = None,
    ) -> Response:
        sess = session if session is not None else auth.read_session(request, self.secret)
        flash = sess.pop("flash", None) if sess else None
        locale = resolve_locale(request.cookies.get(LANG_COOKIE), request.headers.get("accept-language"))
        theme = resolve_theme(request.cookies.get(THEME_COOKIE))
        t = Translator(locale)
        if isinstance(flash, dict) and flash.get("key"):
            flash = {
                "kind": flash.get("kind", "ok"),
                "text": t(flash["key"], **(flash.get("args") or {})),
            }
        ctx = {
            "prefix": self.prefix,
            "desk_title": self.title or (self.app.title if self.app else "Pyron"),
            "user": user,
            "flash": flash,
            "models": self.visible_models(user) if user is not None else self.models(),
            "nav": context.get("nav") or "desk",
            "csrf": sess.get("csrf") if sess else "",
            "core": _core_label(),
            "t": t,
            "locale": locale,
            "theme": theme,
            "locales": LOCALES,
            "locale_labels": LOCALE_LABELS,
            "themes": THEMES,
            "asset_v": _asset_v(),
            **context,
        }
        models = ctx.get("models") or []
        ctx.setdefault(
            "site_models",
            [m for m in models if getattr(m, "slug", None) == "pages"],
        )
        ctx.setdefault(
            "data_models",
            [m for m in models if getattr(m, "slug", None) != "pages"],
        )
        resp = self.templates.render_sync(request, name, ctx, status_code=status)
        if sess is not None:
            if flash:
                sess["flash"] = None
                sess.pop("flash", None)
            auth.write_session(resp, sess, self.secret, self.prefix)
        return resp

    def _flash(self, sess: dict[str, Any], kind: str, key: str, **args: object) -> None:
        sess["flash"] = {"kind": kind, "key": key, "args": args}

    def _t(self, request: Request) -> Translator:
        return Translator(
            resolve_locale(request.cookies.get(LANG_COOKIE), request.headers.get("accept-language"))
        )

    async def prefs_view(self, request: Request):
        lang = request.query_params.get("lang")
        theme = request.query_params.get("theme")
        ajax = request.headers.get("x-pyron-prefs") == "1"
        nxt = request.query_params.get("next") or ""
        if not nxt.startswith(self.prefix):
            nxt = self.url("/")
        resp = Response(status_code=204) if ajax else RedirectResponse(nxt, status_code=303)
        cookie_kw = {"max_age": 365 * 24 * 3600, "path": self.prefix, "samesite": "lax"}
        if lang in LOCALES:
            resp.set_cookie(LANG_COOKIE, lang, **cookie_kw)
        if theme in THEMES:
            resp.set_cookie(THEME_COOKIE, theme, **cookie_kw)
        return resp

    def _redirect(self, path: str, sess: dict[str, Any] | None = None) -> Response:
        resp = RedirectResponse(self.url(path), status_code=303)
        if sess is not None:
            auth.write_session(resp, sess, self.secret, self.prefix)
        return resp

    def _count_users(self) -> int:
        from sqlmodel import func, select

        Model = self.user_model()
        with self.session() as db:
            return int(db.exec(select(func.count()).select_from(Model)).one() or 0)

    def _user_from_session(self, sess: dict[str, Any]) -> Any | None:
        uid = sess.get("uid")
        if not uid:
            return None
        with self.session() as db:
            return auth.load_auth_user(db, int(uid))

    def _gate(self, request: Request) -> tuple[Any, dict[str, Any]] | Response:
        self.ensure_tables()
        sess = auth.read_session(request, self.secret)
        if self._count_users() == 0:
            return self._redirect("/setup", sess)
        user = self._user_from_session(sess)
        if user is None:
            nxt = request.url.path
            return self._redirect(f"/login?next={nxt}", sess)
        if "csrf" not in sess:
            sess["csrf"] = auth.new_csrf()
        return user, sess

    def _check_csrf(self, request: Request, sess: dict[str, Any], form: Any) -> str | None:
        token = str(form.get("csrf") or "")
        if not token or not sess.get("csrf") or token != sess["csrf"]:
            return "This form expired. Reload the page and try again."
        return None

    # ------------------------------------------------------------------
    # Setup / login
    # ------------------------------------------------------------------

    async def setup_view(self, request: Request):
        self.ensure_tables()
        sess = auth.read_session(request, self.secret)
        if self._count_users() > 0:
            return self._redirect("/login", sess)
        error = ""
        username = ""
        if request.method == "POST":
            form = await request.form()
            username = str(form.get("username") or "").strip()
            password = str(form.get("password") or "")
            confirm = str(form.get("confirm") or "")
            csrf_err = self._check_csrf(request, sess, form)
            from pyron.security import password_issues
            from pyron.settings import load_settings

            policy = password_issues(
                password, username=username, min_length=load_settings().password_min_length
            )
            if csrf_err:
                error = csrf_err
            elif len(username) < 2:
                error = "Pick a username with at least two characters."
            elif policy:
                error = " ".join(policy)
            elif password != confirm:
                error = "The two passwords do not match. Type them again."
            else:
                Model = self.user_model()
                with self.session() as db:
                    user = Model(
                        username=username,
                        password_hash=auth.hash_password(password),
                        is_root=True,
                        is_active=True,
                    )
                    db.add(user)
                    db.commit()
                    db.refresh(user)
                    uid = user.id
                sess = {"uid": uid, "csrf": auth.new_csrf()}
                self._flash(sess, "ok", "root_created")
                return self._redirect("/", sess)
        if "csrf" not in sess:
            sess["csrf"] = auth.new_csrf()
        return self._render(
            request,
            "setup.html",
            {
                "nav": "setup",
                "error": error,
                "username": username,
            },
            session=sess,
        )

    async def login_view(self, request: Request):
        self.ensure_tables()
        sess = auth.read_session(request, self.secret)
        if self._count_users() == 0:
            return self._redirect("/setup", sess)
        if self._user_from_session(sess):
            return self._redirect("/", sess)
        error = ""
        username = ""
        nxt = request.query_params.get("next") or self.url("/")
        if request.method == "POST":
            form = await request.form()
            username = str(form.get("username") or "").strip()
            password = str(form.get("password") or "")
            nxt = str(form.get("next") or nxt)
            csrf_err = self._check_csrf(request, sess, form)
            Model = self.user_model()
            from sqlmodel import select

            from pyron.security import client_key, dummy_password_hash, login_throttle
            from pyron.settings import load_settings

            cfg = load_settings()
            ip = client_key(request.scope, trust_proxy=cfg.trust_proxy_headers)
            tr = self._t(request)
            if login_throttle.blocked(ip):
                wait = login_throttle.retry_in(ip)
                error = tr("login_locked", n=wait)
            else:
                with self.session() as db:
                    user = db.exec(select(Model).where(Model.username == username)).first()
                hashed = user.password_hash if user is not None else dummy_password_hash()
                password_ok = auth.verify_password(password, hashed)
                generic = tr("login_mismatch")
                if csrf_err:
                    error = tr("form_expired")
                elif user is None or not password_ok:
                    login_throttle.fail(ip)
                    if cfg.debug:
                        error = (
                            tr("login_no_user", username=username, db=self.engine_label())
                            if user is None
                            else tr("login_bad_password")
                        )
                    else:
                        error = generic
                elif not user.is_active:
                    error = tr("login_deactivated")
                else:
                    login_throttle.success(ip)
                    sess = {"uid": user.id, "csrf": auth.new_csrf()}
                    self._flash(sess, "ok", "signed_in", username=user.username)
                    dest = nxt if nxt.startswith(self.prefix) else self.url("/")
                    resp = RedirectResponse(dest, status_code=303)
                    auth.write_session(resp, sess, self.secret, self.prefix)
                    return resp
        if "csrf" not in sess:
            sess["csrf"] = auth.new_csrf()
        return self._render(
            request,
            "login.html",
            {
                "nav": "login",
                "error": error,
                "username": username,
                "next": nxt,
                "engine_label": self.engine_label(),
            },
            session=sess,
        )

    async def logout_view(self, request: Request):
        resp = RedirectResponse(self.url("/login"), status_code=303)
        auth.clear_session(resp, self.prefix)
        return resp

    # ------------------------------------------------------------------
    # Desk + routes
    # ------------------------------------------------------------------

    async def desk_view(self, request: Request):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        cards = []
        for bound in self.visible_models(user):
            try:
                n = bound.store.count(bound.model) if bound.store is not None else 0
            except Exception:
                n = 0
            cards.append({"bound": bound, "count": n})
        site_cards = [c for c in cards if c["bound"].slug == "pages"]
        data_cards = [c for c in cards if c["bound"].slug != "pages"]
        from pyron.siteconfig import load_site

        site = load_site(
            self.engine,
            fallback=self.title or (self.app.title if self.app else "Pyron"),
        )
        return self._render(
            request,
            "desk.html",
            {
                "nav": "desk",
                "cards": cards,
                "site_cards": site_cards,
                "data_cards": data_cards,
                "site": site,
                "pages_enabled": self.pages_enabled,
                "user_count": self._count_users(),
                "route_count": len(getattr(self.app, "routes", []) or []),
            },
            session=sess,
            user=user,
        )

    async def settings_view(self, request: Request):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        from pyron.siteconfig import clean_site_values, load_site, save_site

        fallback = self.title or (self.app.title if self.app else "Pyron")
        site = load_site(self.engine, fallback=fallback)
        error = ""
        form = {
            "name": site.name,
            "tagline": site.tagline,
            "phone": site.phone,
            "email": site.email,
            "hours": site.hours,
            "address": site.address,
            "website": site.website,
        }
        if request.method == "POST":
            posted = await request.form()
            csrf_err = self._check_csrf(request, sess, posted)
            form = {key: str(posted.get(key) or "") for key in form}
            if csrf_err:
                error = csrf_err
            else:
                try:
                    cleaned = clean_site_values(form, fallback=fallback)
                    site = save_site(self.engine, cleaned)
                    self._flash(sess, "ok", "settings_saved")
                    return self._redirect("/settings", sess)
                except ValueError as exc:
                    error = str(exc)
        return self._render(
            request,
            "settings.html",
            {"nav": "settings", "error": error, "form": form, "site": site},
            session=sess,
            user=user,
        )

    async def preview_markdown(self, request: Request):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        _user, sess = gated
        posted = await request.form()
        csrf_err = self._check_csrf(request, sess, posted)
        if csrf_err:
            from pyron.responses import HTMLResponse

            return HTMLResponse(csrf_err, status_code=400)
        from pyron.pages import render_page_body
        from pyron.responses import HTMLResponse

        html = render_page_body(str(posted.get("body") or ""))
        if not html:
            t = self._t(request)
            html = f'<p class="empty">{t("preview_empty")}</p>'
        return HTMLResponse(html)

    async def routes_view(self, request: Request):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        rows = []
        for route in getattr(self.app, "routes", []) or []:
            rows.append(
                {
                    "methods": ", ".join(route.methods),
                    "path": route.path,
                    "name": route.name,
                    "tags": ", ".join(route.tags or []),
                    "admin": route.path.startswith(self.prefix),
                }
            )
        rows.sort(key=lambda r: (r["admin"], r["path"]))
        return self._render(
            request,
            "routes.html",
            {"nav": "routes", "rows": rows},
            session=sess,
            user=user,
        )

    # ------------------------------------------------------------------
    # Users (root only)
    # ------------------------------------------------------------------

    async def users_list(self, request: Request):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        if not user.is_root:
            from pyron.authz import PermissionDenied

            raise PermissionDenied("root")
        Model = self.user_model()
        from sqlmodel import select

        with self.session() as db:
            people = db.exec(select(Model).order_by(Model.username)).all()
        return self._render(
            request,
            "users_list.html",
            {"nav": "users", "people": people},
            session=sess,
            user=user,
        )

    async def user_new(self, request: Request):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        if not user.is_root:
            from pyron.authz import PermissionDenied

            raise PermissionDenied("root")
        error = ""
        form_data = {"username": "", "is_root": False, "is_active": True}
        if request.method == "POST":
            form = await request.form()
            csrf_err = self._check_csrf(request, sess, form)
            username = str(form.get("username") or "").strip()
            password = str(form.get("password") or "")
            is_root = "is_root" in form
            form_data = {"username": username, "is_root": is_root, "is_active": True}
            if csrf_err:
                error = csrf_err
            elif len(username) < 2:
                error = "Pick a username with at least two characters."
            elif len(password) < 8:
                error = "Use at least 8 characters for the password."
            else:
                Model = self.user_model()
                from sqlmodel import select

                with self.session() as db:
                    exists = db.exec(select(Model).where(Model.username == username)).first()
                    if exists:
                        error = f"Someone already uses the username “{username}”."
                    else:
                        person = Model(
                            username=username,
                            password_hash=auth.hash_password(password),
                            is_root=is_root,
                            is_active=True,
                        )
                        db.add(person)
                        db.commit()
                        db.refresh(person)
                        if not is_root:
                            auth.add_user_to_staff(db, person)
                            db.commit()
                if not error:
                    self._flash(sess, "ok", "created_operator", username=username)
                    return self._redirect("/users", sess)
        return self._render(
            request,
            "user_form.html",
            {"nav": "users", "error": error, "form": form_data, "creating": True, "person": None},
            session=sess,
            user=user,
        )

    async def user_edit(self, request: Request, user_id: int):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        actor, sess = gated
        if not actor.is_root:
            from pyron.authz import PermissionDenied

            raise PermissionDenied("root")
        Model = self.user_model()
        with self.session() as db:
            person = db.get(Model, user_id)
        if person is None:
            raise HTTPException(404, "That operator does not exist.")
        error = ""
        if request.method == "POST":
            form = await request.form()
            csrf_err = self._check_csrf(request, sess, form)
            if csrf_err:
                error = csrf_err
            else:
                username = str(form.get("username") or "").strip() or person.username
                password = str(form.get("password") or "")
                is_root = "is_root" in form
                is_active = "is_active" in form
                if person.id == actor.id and not is_root:
                    error = "You cannot drop root on your own account."
                elif person.id == actor.id and not is_active:
                    error = "You cannot deactivate yourself. Ask another root."
                elif len(username) < 2:
                    error = "Pick a username with at least two characters."
                elif password and len(password) < 8:
                    error = "New passwords need at least 8 characters. Leave the field blank to keep the current one."
                else:
                    with self.session() as db:
                        row = db.get(Model, user_id)
                        row.username = username
                        row.is_root = is_root
                        row.is_active = is_active
                        if password:
                            row.password_hash = auth.hash_password(password)
                        db.add(row)
                        db.commit()
                    self._flash(sess, "ok", "updated_operator", username=username)
                    return self._redirect("/users", sess)
                person.username = username
                person.is_root = is_root
                person.is_active = is_active
        return self._render(
            request,
            "user_form.html",
            {
                "nav": "users",
                "error": error,
                "form": {
                    "username": person.username,
                    "is_root": person.is_root,
                    "is_active": person.is_active,
                },
                "creating": False,
                "person": person,
            },
            session=sess,
            user=actor,
        )

    # ------------------------------------------------------------------
    # Model CRUD
    # ------------------------------------------------------------------

    async def model_list(self, request: Request, slug: str):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        bound = self.get(slug)
        self._require_perm(user, slug, "view")
        q = (request.query_params.get("q") or "").strip()
        filters = self._active_filters(bound, request)
        try:
            page = max(1, int(request.query_params.get("page") or 1))
        except ValueError:
            page = 1
        per = bound.admin.list_per_page
        rows, total = bound.store.list(
            bound.model,
            q=q,
            search_fields=bound.admin.search_fields,
            filters=filters,
            order=bound.admin.ordering,
            offset=(page - 1) * per,
            limit=per,
            pk=bound.pk,
        )
        filter_specs = self._filter_specs(bound)
        pages = max(1, math.ceil(total / per)) if per else 1
        records = []
        for row in rows:
            records.append(
                {
                    "pk": getattr(row, bound.pk),
                    "cells": [insp.display(getattr(row, col, None)) for col in bound.list_display],
                }
            )
        for spec in filter_specs:
            wired = []
            for value, label in spec["choices"]:
                chosen = dict(filters)
                if value in ("", "all"):
                    chosen.pop(spec["name"], None)
                else:
                    chosen[spec["name"]] = value
                wired.append({"value": value, "label": label, "qs": _qs(q, chosen)})
            spec["choices"] = wired
        return self._render(
            request,
            "model_list.html",
            {
                "nav": f"m:{slug}",
                "bound": bound,
                "headers": [c.replace("_", " ") for c in bound.list_display],
                "records": records,
                "q": q,
                "page": page,
                "pages": pages,
                "total": total,
                "can_add": bound.admin.can_create and user.has_perm(f"{slug}.add"),
                "can_change": bound.admin.can_edit and user.has_perm(f"{slug}.change"),
                "can_delete": bound.admin.can_delete and user.has_perm(f"{slug}.delete"),
                "filter_specs": filter_specs,
                "active_filters": filters,
                "prev_qs": _qs(q, filters, page=page - 1) if page > 1 else "",
                "next_qs": _qs(q, filters, page=page + 1) if page < pages else "",
            },
            session=sess,
            user=user,
        )

    async def model_new(self, request: Request, slug: str):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        bound = self.get(slug)
        if not bound.admin.can_create:
            raise HTTPException(403, "Creating is turned off for this table.")
        self._require_perm(user, slug, "add")
        values, error = await self._bind_form(request, bound, None, sess)
        if request.method == "POST" and not error:
            try:
                obj = bound.store.insert(bound.model, values, pk=bound.pk)
            except Exception as exc:
                error = _save_error(exc) or error
                obj = None
            if obj is not None:
                pk = getattr(obj, bound.pk)
                self._log(user.username, "add", slug, pk, _obj_label(obj, bound))
                self._flash(sess, "ok", "added_model", name=bound.name, pk=pk)
                if str((await request.form()).get("intent") or "") == "continue":
                    return self._redirect(f"/m/{slug}/{pk}", sess)
                return self._redirect(f"/m/{slug}", sess)
        return self._render(
            request,
            "model_form.html",
            {
                "nav": f"m:{slug}",
                "bound": bound,
                "creating": True,
                "error": error,
                "fields": _form_fields(bound, values),
                "pk": None,
                "can_delete": False,
                "view_url": None,
            },
            session=sess,
            user=user,
        )

    async def model_edit(self, request: Request, slug: str, pk: str):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        bound = self.get(slug)
        obj = self._load(bound, pk)
        if obj is None:
            raise HTTPException(404, f"No {bound.name} with id {pk}.")
        self._require_perm(user, slug, "view")
        if request.method == "POST":
            if not bound.admin.can_edit:
                raise HTTPException(403, "Editing is turned off for this table.")
            self._require_perm(user, slug, "change")
        values, error = await self._bind_form(request, bound, obj, sess)
        if request.method == "POST" and not error:
            try:
                row = bound.store.update(bound.model, pk, values, pk=bound.pk)
            except Exception as exc:
                error = _save_error(exc) or error
                row = None
            if row is not None:
                self._log(user.username, "change", slug, pk, _obj_label(row, bound))
                if bound.kind == "sql":
                    await self._save_inlines(request, bound, pk)
                self._flash(sess, "ok", "saved_model", name=bound.name, pk=pk)
                form = await request.form()
                if str(form.get("intent") or "") == "continue":
                    return self._redirect(f"/m/{slug}/{pk}", sess)
                return self._redirect(f"/m/{slug}", sess)
        return self._render(
            request,
            "model_form.html",
            {
                "nav": f"m:{slug}",
                "bound": bound,
                "creating": False,
                "error": error,
                "fields": _form_fields(bound, values, obj),
                "pk": pk,
                "can_delete": bound.admin.can_delete and user.has_perm(f"{slug}.delete"),
                "history": self._history(slug, pk),
                "inline_blocks": self._inline_blocks(bound, pk),
                "view_url": _view_url(bound, obj),
            },
            session=sess,
            user=user,
        )

    async def model_delete(self, request: Request, slug: str, pk: str):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        bound = self.get(slug)
        if not bound.admin.can_delete:
            raise HTTPException(403, "Deleting is turned off for this table.")
        self._require_perm(user, slug, "delete")
        obj = self._load(bound, pk)
        if obj is None:
            raise HTTPException(404, f"No {bound.name} with id {pk}.")
        label = _obj_label(obj, bound)
        if request.method == "POST":
            form = await request.form()
            err = self._check_csrf(request, sess, form)
            if err:
                return self._render(
                    request,
                    "model_delete.html",
                    {"nav": f"m:{slug}", "bound": bound, "pk": pk, "label": label, "error": err},
                    session=sess,
                    user=user,
                )
            self._log(user.username, "delete", slug, pk, label)
            bound.store.delete(bound.model, pk, pk=bound.pk)
            self._flash(sess, "ok", "deleted_model", name=bound.name, label=label)
            return self._redirect(f"/m/{slug}", sess)
        return self._render(
            request,
            "model_delete.html",
            {"nav": f"m:{slug}", "bound": bound, "pk": pk, "label": label, "error": ""},
            session=sess,
            user=user,
        )

    def _active_filters(self, bound: _Bound, request: Request) -> dict[str, str]:
        names = bound.admin.list_filter or []
        out: dict[str, str] = {}
        for name in names:
            raw = request.query_params.get(f"f_{name}")
            if raw not in (None, "", "all"):
                out[name] = raw
        return out

    def _filter_specs(self, bound: _Bound) -> list[dict[str, Any]]:
        specs = []
        for name in bound.admin.list_filter or []:
            field = bound.model.model_fields.get(name)
            if field is None:
                continue
            python = insp.python_type(field.annotation)
            if python is bool:
                choices = [("all", "all"), ("true", "yes"), ("false", "no")]
            else:
                vals = bound.store.distinct(bound.model, name) if bound.store is not None else []
                choices = [("all", "all")] + [(str(v), str(v)) for v in vals if v is not None]
            specs.append({"name": name, "label": name.replace("_", " "), "choices": choices})
        return specs

    async def model_action(self, request: Request, slug: str):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        form = await request.form()
        ids = [str(v) for v in form.getlist("pk") if str(v)]
        action = str(form.get("action") or "")
        if action != "delete_selected" or not ids:
            return self._redirect(f"/m/{slug}", sess)
        self._require_perm(user, slug, "delete")
        sess["bulk_ids"] = ids
        sess["bulk_action"] = action
        return self._redirect(f"/m/{slug}/action/confirm", sess)

    async def model_action_confirm(self, request: Request, slug: str):
        gated = self._gate(request)
        if isinstance(gated, Response):
            return gated
        user, sess = gated
        bound = self.get(slug)
        ids = list(sess.get("bulk_ids") or [])
        if not ids:
            return self._redirect(f"/m/{slug}", sess)
        self._require_perm(user, slug, "delete")
        labels = []
        for raw in ids:
            row = bound.store.get(bound.model, raw, pk=bound.pk)
            if row is not None:
                labels.append(_obj_label(row, bound))
        if request.method == "POST":
            form = await request.form()
            err = self._check_csrf(request, sess, form)
            if err:
                return self._render(
                    request,
                    "model_bulk.html",
                    {
                        "nav": f"m:{slug}",
                        "bound": bound,
                        "labels": labels,
                        "error": err,
                    },
                    session=sess,
                    user=user,
                )
            for raw in ids:
                row = bound.store.get(bound.model, raw, pk=bound.pk)
                if row is None:
                    continue
                self._log(user.username, "delete", slug, raw, _obj_label(row, bound))
                bound.store.delete(bound.model, raw, pk=bound.pk)
            sess.pop("bulk_ids", None)
            sess.pop("bulk_action", None)
            self._flash(sess, "ok", "deleted_model", name=bound.plural, label=str(len(labels)))
            return self._redirect(f"/m/{slug}", sess)
        return self._render(
            request,
            "model_bulk.html",
            {"nav": f"m:{slug}", "bound": bound, "labels": labels, "error": ""},
            session=sess,
            user=user,
        )

    def _history(self, slug: str, pk: str) -> list[Any]:
        from sqlmodel import select

        Log = auth.log_model()
        with self.session() as db:
            return list(
                db.exec(
                    select(Log)
                    .where(Log.slug == slug, Log.object_pk == str(pk))
                    .order_by(Log.created_at.desc())
                    .limit(20)
                ).all()
            )

    def _inline_blocks(self, bound: _Bound, pk: str) -> list[dict[str, Any]]:
        if bound.kind != "sql":
            return []
        blocks = []
        from sqlmodel import select

        for spec in bound.admin.inlines or []:
            inline = spec() if isinstance(spec, type) else spec
            child = inline.model
            if child is None:
                continue
            fk = inline.fk_name or _guess_fk(child, bound.model)
            if not fk:
                continue
            with self.session() as db:
                rows = list(db.exec(select(child).where(getattr(child, fk) == _pk_cast_raw(bound, pk))).all())
            child_bound = _Bound(child, ModelAdmin(child))
            items = []
            for row in rows:
                items.append(
                    {
                        "pk": getattr(row, child_bound.pk),
                        "fields": _form_fields(child_bound, {}, row),
                    }
                )
            blocks.append(
                {
                    "slug": child_bound.slug,
                    "name": child_bound.plural,
                    "fk": fk,
                    "rows": items,
                    "extra": inline.extra,
                    "blank_fields": _form_fields(child_bound, {}, None),
                }
            )
        return blocks

    async def _save_inlines(self, request: Request, bound: _Bound, pk: str) -> None:
        if not bound.admin.inlines:
            return
        form = await request.form()
        from sqlmodel import select

        parent_key = _pk_cast_raw(bound, pk)
        with self.session() as db:
            for spec in bound.admin.inlines or []:
                inline = spec() if isinstance(spec, type) else spec
                child = inline.model
                if child is None:
                    continue
                fk = inline.fk_name or _guess_fk(child, bound.model)
                if not fk:
                    continue
                child_bound = _Bound(child, ModelAdmin(child))
                # updates
                for row in db.exec(select(child).where(getattr(child, fk) == parent_key)).all():
                    rid = getattr(row, child_bound.pk)
                    prefix = f"inline-{child_bound.slug}-{rid}-"
                    if form.get(prefix + "DELETE"):
                        db.delete(row)
                        continue
                    for field in child_bound.fields:
                        if field["primary_key"] or field["name"] == fk:
                            continue
                        key = prefix + field["name"]
                        if key in form:
                            try:
                                setattr(row, field["name"], insp.coerce(field, form.get(key)))
                            except ValueError:
                                pass
                    db.add(row)
                extra = inline.extra or 0
                for i in range(extra):
                    prefix = f"inline-{child_bound.slug}-new{i}-"
                    payload = {}
                    empty = True
                    for field in child_bound.fields:
                        if field["primary_key"] or field["name"] == fk or field["auto"]:
                            continue
                        raw = form.get(prefix + field["name"])
                        if raw not in (None, ""):
                            empty = False
                            try:
                                payload[field["name"]] = insp.coerce(field, raw)
                            except ValueError:
                                payload[field["name"]] = raw
                    if not empty:
                        payload[fk] = parent_key
                        db.add(child(**payload))
            db.commit()

    def _log(self, username: str, action: str, slug: str, pk: Any, label: str) -> None:
        if self.engine is None:
            return
        with self.session() as db:
            auth.write_log(db, username=username, action=action, slug=slug, pk=pk, label=label)
            db.commit()

    def _load(self, bound: _Bound, pk: str) -> Any | None:
        if bound.store is None:
            return None
        return bound.store.get(bound.model, pk, pk=bound.pk)

    async def _bind_form(
        self,
        request: Request,
        bound: _Bound,
        obj: Any | None,
        sess: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        values: dict[str, Any] = {}
        if obj is not None:
            for spec in bound.fields:
                if spec["auto"] and spec["primary_key"]:
                    continue
                values[spec["name"]] = getattr(obj, spec["name"], None)
        else:
            for spec in bound.fields:
                if spec["auto"] and spec["primary_key"]:
                    continue
                default = _field_default(bound.model, spec["name"])
                if default is not _UNSET:
                    values[spec["name"]] = default
        if request.method != "POST":
            return values, ""
        form = await request.form()
        csrf_err = self._check_csrf(request, sess, form)
        if csrf_err:
            return values, csrf_err
        errors: list[str] = []
        out: dict[str, Any] = {}
        posted = {k: form.get(k) for k in form.keys()}
        for spec in bound.fields:
            if spec["auto"] and (obj is None or spec["primary_key"]):
                continue
            if spec["widget"] == "checkbox":
                raw = spec["name"] in posted
            else:
                raw = posted.get(spec["name"])
            try:
                out[spec["name"]] = insp.coerce(spec, raw)
            except ValueError as exc:
                errors.append(str(exc))
                out[spec["name"]] = raw
        values.update(out)
        if errors:
            return values, " ".join(errors)
        cleaner = getattr(bound.admin, "clean", None)
        if callable(cleaner):
            try:
                cleaned = cleaner(values)
                if isinstance(cleaned, dict):
                    values = cleaned
            except ValueError as exc:
                return values, str(exc)
        return values, ""


def _qs(q: str, filters: dict[str, str], *, page: int | None = None) -> str:
    from urllib.parse import urlencode

    pairs: list[tuple[str, str]] = []
    if q:
        pairs.append(("q", q))
    for key, value in filters.items():
        pairs.append((f"f_{key}", value))
    if page and page > 1:
        pairs.append(("page", str(page)))
    return urlencode(pairs)


def _pk_cast_raw(bound: _Bound, pk: str) -> Any:
    field = bound.model.model_fields.get(bound.pk)
    if field is not None and insp.python_type(field.annotation) is int:
        try:
            return int(pk)
        except ValueError:
            return pk
    return pk


def _guess_fk(child: type, parent: type) -> str | None:
    table = getattr(child, "__table__", None)
    parent_table = getattr(parent, "__tablename__", None) or getattr(getattr(parent, "__table__", None), "name", None)
    if table is None or not parent_table:
        return None
    for col in table.columns:
        for fk in col.foreign_keys:
            if fk.column.table.name == parent_table:
                return col.name
    return None


def _obj_label(obj: Any, bound: _Bound) -> str:
    for attr in ("title", "name", "username", "slug"):
        if hasattr(obj, attr):
            val = getattr(obj, attr)
            if val:
                return str(val)
    return f"#{getattr(obj, bound.pk)}"


def _save_error(exc: BaseException) -> str | None:
    msg = str(exc).lower()
    if "unique" in msg or "integrity" in msg:
        if "slug" in msg:
            return "That slug is already used. Pick another."
        return "That record already exists."
    return None


def _view_url(bound: _Bound, obj: Any) -> str | None:
    fn = getattr(bound.admin, "view_on_site", None)
    if not callable(fn) or obj is None:
        return None
    try:
        url = fn(obj)
    except Exception:
        return None
    return url if isinstance(url, str) and url.startswith("/") else None


_UNSET = object()


def _field_default(model: type, name: str) -> Any:
    field = getattr(model, "model_fields", {}).get(name)
    if field is None:
        return _UNSET
    factory = getattr(field, "default_factory", None)
    if factory is not None:
        try:
            return factory()
        except Exception:
            return _UNSET
    try:
        from pydantic_core import PydanticUndefined
    except Exception:
        PydanticUndefined = object()
    default = getattr(field, "default", PydanticUndefined)
    if default is PydanticUndefined:
        return _UNSET
    return default


def _form_fields(bound: _Bound, values: dict[str, Any], obj: Any | None = None) -> list[dict[str, Any]]:
    out = []
    for spec in bound.fields:
        if spec["auto"] and obj is None:
            continue
        value = values.get(spec["name"])
        if value is None and obj is not None:
            value = getattr(obj, spec["name"], None)
        item = dict(spec)
        item["value"] = insp.form_value(value, spec["widget"])
        item["checked"] = bool(value) if spec["widget"] == "checkbox" else False
        if spec["widget"] == "markdown":
            from pyron.pages import render_page_body

            item["preview_html"] = render_page_body(str(value or ""))
        out.append(item)
    return out


def _core_label() -> str:
    try:
        from pyron._bridge import CORE

        return str(CORE)
    except Exception:
        return "python"


def _asset_v() -> str:
    latest = 0.0
    for name in ("desk.css", "desk.js"):
        path = ASSETS_DIR / name
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            pass
    return str(int(latest)) if latest else "0"


class _AdminAssets(StaticFiles):
    def __init__(self) -> None:
        super().__init__(directory=str(ASSETS_DIR))

    async def get_response(self, path: str, scope: Any) -> Any:
        response = await super().get_response(path, scope)
        from pyron.settings import load_settings

        if not load_settings().production:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
