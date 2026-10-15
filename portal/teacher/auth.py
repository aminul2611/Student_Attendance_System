from functools import wraps

from flask import (
    abort,
    g,
    redirect,
    request,
    url_for,
)


def teacher_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(
                url_for(
                    "login",
                    role="teacher",
                    next=request.path,
                )
            )

        if g.user["role"] != "teacher":
            abort(403)

        return view(*args, **kwargs)

    return wrapped