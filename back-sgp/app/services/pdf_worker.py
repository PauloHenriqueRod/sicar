"""Leitura de PDF em processo descartável, sem receber credenciais no ambiente."""
import ctypes
import json
import os
import sys
from pathlib import Path

MEMORY_LIMIT = 512 * 1024 * 1024
MAX_PAGES = 100
MAX_TEXT_CHARS = 1_000_000
_job = None


def limit_memory():
    global _job
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
        return
    from ctypes import wintypes
    size_t = ctypes.c_size_t

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
            ("flags", wintypes.DWORD), ("min_working_set", size_t), ("max_working_set", size_t),
            ("active_processes", wintypes.DWORD), ("affinity", size_t),
            ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD),
        ]

    class IOCounts(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes",
        )]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("basic", BasicLimits), ("io", IOCounts), ("process_memory", size_t),
            ("job_memory", size_t), ("peak_process", size_t), ("peak_job", size_t),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    _job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.process_memory = MEMORY_LIMIT
    if not _job or not kernel.SetInformationJobObject(_job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise OSError("Não foi possível limitar a memória do leitor.")
    if not kernel.AssignProcessToJobObject(_job, kernel.GetCurrentProcess()):
        raise OSError("Não foi possível isolar a memória do leitor.")


def main():
    try:
        limit_memory()
    except Exception:
        print(json.dumps({"status": "unavailable"}))
        return
    try:
        import pdfplumber
        with pdfplumber.open(sys.argv[1]) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                print(json.dumps({"status": "limit"}))
                return
            chunks, pages, count = [], [], 0
            source_pdf = len(sys.argv) > 2 and sys.argv[2] == "fonte:pdf"
            versioned = len(sys.argv) > 2 and (sys.argv[2].startswith("v2:") or source_pdf)
            if versioned:
                sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
                from app.services.extracao_documentos import extrair_documento
            for number, page in enumerate(pdf.pages, 1):
                text = (page.extract_text() or "") + "\n"
                count += len(text)
                if count > MAX_TEXT_CHARS:
                    print(json.dumps({"status": "limit"}))
                    return
                chunks.append(text)
                if versioned:
                    words = page.extract_words()
                    pages.append({"numero": number, "texto": text,
                                  "texto_original": text, "palavras": words,
                                  "largura": page.width})
            if versioned:
                if source_pdf:
                    from app.services.leitores_pdf.tabelas import ler_tabelas
                    print(json.dumps({"status": "ok", "data": {"linhas": ler_tabelas(pages)}}, allow_nan=False))
                    return
                data = {"_extracao_v2": extrair_documento(pages)}
                print(json.dumps({"status": "ok", "data": data}, allow_nan=False))
                return
        text = "".join(chunks)
        if len(sys.argv) > 2:
            # -I evita imports do ambiente; somente o código local conhecido é incluído.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from app.services.dados_pdf import extract_calculation_data
            if sys.argv[2] == "exercicio_anterior":
                data = extract_calculation_data(text, "exercicio_anterior", incluir_fontes_exercicios=True)
            elif sys.argv[2] == "abono":
                data = extract_calculation_data(text, "abono", incluir_fontes_abono=True)
            else:
                data = extract_calculation_data(text, sys.argv[2], incluir_fontes_rescisao=True) if sys.argv[2] == "rescisao" else extract_calculation_data(text, sys.argv[2])
            print(json.dumps({"status": "ok", "data": data}, allow_nan=False))
        else:
            print(json.dumps({"status": "ok", "text": text}))
    except MemoryError:
        print(json.dumps({"status": "limit"}))
    except Exception:
        print(json.dumps({"status": "invalid"}))


if __name__ == "__main__":
    main()
