from pathlib import Path

from .base import BaseSchema


class CheckPaths(BaseSchema):
    name = "validate-paths"
    meta_desc = "Checks that critical path arguments resolve locally and flags broken absolute paths."

    def validate(self, config):
        # The common keys that typically represent local file paths
        path_keys = {
            "output",
            "outdir",
            "cache_dir",
            "file",
            "mask_fn",
            "dem",
            "barrier",
            "path",
        }

        def _check_dict_paths(target_dict, context_name):
            for k, v in target_dict.items():
                if k in path_keys and isinstance(v, str):
                    # Ignore cloud/remote paths
                    if v.startswith(("http", "s3://", "gs://", "ftp://")):
                        continue

                    p = Path(v)
                    # If it is an absolute path, ensure it exists (or its parent directory exists for outputs)
                    if p.is_absolute():
                        parent = p.parent
                        if not parent.exists():
                            self.errors.append(
                                f"[{context_name}] Broken Absolute Path: '{k}' points to '{v}' but the directory does not exist on this machine."
                            )

        for hook in config.get("global_hooks", []):
            h_name = hook.get("name", "Unknown Global Hook")
            _check_dict_paths(hook.get("args", {}), f"Global -> {h_name}")

        for mod in config.get("modules", []):
            m_name = mod.get("module", "Unknown Module")
            _check_dict_paths(mod.get("args", {}), f"Module -> {m_name}")

            for hook in mod.get("hooks", []):
                h_name = hook.get("name", "Unknown Hook")
                _check_dict_paths(hook.get("args", {}), f"Module {m_name} -> {h_name}")
