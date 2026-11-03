import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(workspace: Path) -> None:
    logger = logging.getLogger("aero_ai_studio")
    target = (workspace / "logs" / "app.log").resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            if Path(handler.baseFilename) == target:
                return
            logger.removeHandler(handler)
            handler.close()
    handler = RotatingFileHandler(target, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info("app start workspace=%s", workspace)
