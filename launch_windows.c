#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

static const unsigned char loader_instructions[] = {
    0x48, 0x89, 0x54, 0x24, 0x30, /* mov [rsp+30h], rdx */
    0x4c, 0x89, 0x44, 0x24, 0x38  /* mov [rsp+38h], r8 */
};
static const char upgrade_source[] = "@src/ui/upgrade.lua";
static const size_t max_chunk = 1000000;

typedef struct {
    unsigned char *bytes;
    size_t size;
} Buffer;

static Buffer read_file(const wchar_t *path)
{
    Buffer buffer = {0};
    FILE *file = _wfopen(path, L"rb");
    if (!file) return buffer;
    if (fseek(file, 0, SEEK_END) == 0) {
        long size = ftell(file);
        if (size > 0 && (size_t)size < max_chunk && fseek(file, 0, SEEK_SET) == 0) {
            buffer.bytes = malloc((size_t)size);
            if (buffer.bytes && fread(buffer.bytes, 1, (size_t)size, file) == (size_t)size) {
                buffer.size = (size_t)size;
            }
        }
    }
    fclose(file);
    return buffer;
}

static BOOL read_target(HANDLE process, uintptr_t address, void *data, size_t size)
{
    SIZE_T count = 0;
    return ReadProcessMemory(process, (const void *)address, data, size, &count)
        && count == size;
}

static BOOL write_target(HANDLE process, uintptr_t address, const void *data, size_t size)
{
    SIZE_T count = 0;
    return WriteProcessMemory(process, (void *)address, data, size, &count)
        && count == size;
}

static BOOL set_instruction(HANDLE process, uintptr_t address, unsigned char value)
{
    DWORD protection, ignored;
    if (!VirtualProtectEx(process, (void *)address, 1, PAGE_EXECUTE_READWRITE, &protection)) {
        return FALSE;
    }
    BOOL changed = write_target(process, address, &value, 1);
    BOOL protected = VirtualProtectEx(process, (void *)address, 1, protection, &ignored);
    return changed && protected && FlushInstructionCache(process, (void *)address, 1);
}

static DWORD loader_offset(const wchar_t *directory)
{
    wchar_t path[32768];
    if (swprintf(path, 32768, L"%ls\\lua51.dll", directory) < 0) return 0;
    HMODULE module = LoadLibraryExW(path, NULL, DONT_RESOLVE_DLL_REFERENCES);
    if (!module) return 0;
    FARPROC entry = GetProcAddress(module, "luaL_loadbuffer");
    DWORD offset = entry ? (DWORD)((uintptr_t)entry - (uintptr_t)module + 4) : 0;
    FreeLibrary(module);
    return offset;
}

static BOOL is_lua_module(HANDLE process, const LOAD_DLL_DEBUG_INFO *module)
{
    wchar_t path[32768];
    DWORD size = module->hFile
        ? GetFinalPathNameByHandleW(module->hFile, path, 32768, FILE_NAME_NORMALIZED)
        : 0;
    if (!size || size >= 32768) {
        size = GetMappedFileNameW(process, module->lpBaseOfDll, path, 32768);
    }
    if (!size || size >= 32768) return FALSE;
    path[size] = L'\0';
    const wchar_t *name = wcsrchr(path, L'\\');
    return _wcsicmp(name ? name + 1 : path, L"lua51.dll") == 0;
}

static uintptr_t replacement_chunk(HANDLE process, const CONTEXT *context,
                                   const Buffer *prefix, const Buffer *suffix,
                                   size_t *size)
{
    size_t length = (size_t)context->R8;
    if (length < 10 || length >= max_chunk) return 0;
    unsigned char *original = malloc(length);
    *size = prefix->size + length * 4 + suffix->size;
    unsigned char *replacement = malloc(*size);
    uintptr_t remote = 0;
    if (original && replacement && read_target(process, context->Rdx, original, length)
        && memcmp(original, "\x1bLJ\x02", 4) == 0) {
        memcpy(replacement, prefix->bytes, prefix->size);
        unsigned char *output = replacement + prefix->size;
        for (size_t index = 0; index < length; ++index) {
            unsigned int byte = original[index];
            *output++ = '\\';
            *output++ = (unsigned char)('0' + byte / 100);
            *output++ = (unsigned char)('0' + byte / 10 % 10);
            *output++ = (unsigned char)('0' + byte % 10);
        }
        memcpy(output, suffix->bytes, suffix->size);
        void *memory = VirtualAllocEx(process, NULL, *size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
        if (memory && write_target(process, (uintptr_t)memory, replacement, *size)) {
            remote = (uintptr_t)memory;
        }
    }
    free(original);
    free(replacement);
    return remote;
}

/* Emulate the verified instructions so the loader reads arguments from its
   stack after detaching. Unrelated chunks keep the game's original arguments. */
static int handle_loader(HANDLE process, DWORD thread_id, uintptr_t breakpoint,
                         const Buffer *prefix, const Buffer *suffix)
{
    HANDLE thread = OpenThread(THREAD_GET_CONTEXT | THREAD_SET_CONTEXT, FALSE, thread_id);
    if (!thread) return -1;
    CONTEXT context = {0};
    context.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
    int result = -1;
    if (GetThreadContext(thread, &context)) {
        char name[sizeof(upgrade_source)];
        BOOL target = read_target(process, context.R9, name, sizeof(name))
            && memcmp(name, upgrade_source, sizeof(name)) == 0;
        uintptr_t args[] = {context.Rdx, context.R8};
        size_t argument_count = 1;
        context.Rip = breakpoint + 5;
        if (target) {
            size_t size = 0;
            args[0] = replacement_chunk(process, &context, prefix, suffix, &size);
            args[1] = size;
            argument_count = 2;
            context.Rip = breakpoint + sizeof(loader_instructions);
        }
        if (args[0] && write_target(process, context.Rsp + 0x30, args, argument_count * sizeof(args[0]))
            && SetThreadContext(thread, &context)
            && (!target || set_instruction(process, breakpoint, loader_instructions[0]))) {
            result = target ? 1 : 0;
        }
    }
    CloseHandle(thread);
    return result;
}

static BOOL patch_game(const PROCESS_INFORMATION *child, DWORD offset,
                       const Buffer *prefix, const Buffer *suffix)
{
    HANDLE process = child->hProcess;
    uintptr_t breakpoint = 0;
    BOOL first_breakpoint = TRUE;
    ULONGLONG deadline = GetTickCount64() + 25000;
    while (GetTickCount64() < deadline) {
        DEBUG_EVENT event;
        if (!WaitForDebugEvent(&event, 250)) {
            if (GetLastError() == ERROR_SEM_TIMEOUT) continue;
            break;
        }
        DWORD outcome = DBG_CONTINUE;
        int patched = 0;
        if (event.dwDebugEventCode == CREATE_PROCESS_DEBUG_EVENT) {
            if (event.u.CreateProcessInfo.hFile) CloseHandle(event.u.CreateProcessInfo.hFile);
        } else if (event.dwDebugEventCode == LOAD_DLL_DEBUG_EVENT) {
            const LOAD_DLL_DEBUG_INFO *dll = &event.u.LoadDll;
            if (!breakpoint && is_lua_module(process, dll)) {
                breakpoint = (uintptr_t)dll->lpBaseOfDll + offset;
                unsigned char actual[sizeof(loader_instructions)];
                if (!read_target(process, breakpoint, actual, sizeof(actual))
                    || memcmp(actual, loader_instructions, sizeof(actual)) != 0
                    || !set_instruction(process, breakpoint, 0xcc)) {
                    fputs("Unsupported Slotbound Lua runtime layout.\n", stderr);
                    patched = -1;
                }
            }
            if (dll->hFile) CloseHandle(dll->hFile);
        } else if (event.dwDebugEventCode == EXCEPTION_DEBUG_EVENT) {
            const EXCEPTION_RECORD *ex = &event.u.Exception.ExceptionRecord;
            outcome = DBG_EXCEPTION_NOT_HANDLED;
            if (ex->ExceptionCode == EXCEPTION_BREAKPOINT) {
                if (breakpoint && (uintptr_t)ex->ExceptionAddress == breakpoint) {
                    patched = handle_loader(process, event.dwThreadId, breakpoint, prefix, suffix);
                    outcome = DBG_CONTINUE;
                } else if (first_breakpoint) {
                    first_breakpoint = FALSE;
                    outcome = DBG_CONTINUE;
                }
            }
        } else if (event.dwDebugEventCode == EXIT_PROCESS_DEBUG_EVENT) {
            ContinueDebugEvent(event.dwProcessId, event.dwThreadId, DBG_CONTINUE);
            fputs("Slotbound exited before loading its upgrade module.\n", stderr);
            return FALSE;
        }
        if (patched < 0) {
            TerminateProcess(process, 1);
            ContinueDebugEvent(event.dwProcessId, event.dwThreadId, DBG_CONTINUE);
            break;
        }
        if (!ContinueDebugEvent(event.dwProcessId, event.dwThreadId, outcome)) break;
        if (patched > 0) {
            if (DebugActiveProcessStop(child->dwProcessId)) return TRUE;
            break;
        }
    }
    fputs("The game did not accept the local probability configuration.\n", stderr);
    TerminateProcess(process, 1);
    return FALSE;
}

int wmain(int argc, wchar_t **argv)
{
    if (argc != 4) return 2;
    const wchar_t *slash = wcsrchr(argv[1], L'\\');
    if (!slash || _wcsicmp(slash + 1, L"Slotbound.exe") != 0) return 2;
    wchar_t directory[32768], command[32768];
    size_t length = (size_t)(slash - argv[1]);
    if (length + 1 >= 32768 || swprintf(command, 32768, L"\"%ls\"", argv[1]) < 0) return 2;
    memcpy(directory, argv[1], length * sizeof(wchar_t));
    directory[length] = L'\0';

    DWORD offset = loader_offset(directory);
    if (!offset) {
        fputs("Could not locate Slotbound's Lua loader.\n", stderr);
        return 2;
    }
    Buffer prefix = read_file(argv[2]), suffix = read_file(argv[3]);
    int status = 2;
    if (prefix.size && suffix.size) {
        STARTUPINFOW startup = {0};
        startup.cb = sizeof(startup);
        PROCESS_INFORMATION child;
        if (CreateProcessW(argv[1], command, NULL, NULL, FALSE, DEBUG_ONLY_THIS_PROCESS,
                           NULL, directory, &startup, &child)) {
            status = patch_game(&child, offset, &prefix, &suffix) ? 0 : 1;
            CloseHandle(child.hThread);
            CloseHandle(child.hProcess);
        } else {
            fprintf(stderr, "Could not start Slotbound (Windows error %lu).\n", GetLastError());
        }
    }
    free(prefix.bytes);
    free(suffix.bytes);
    return status;
}
