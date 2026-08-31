/* SPDX-License-Identifier: MIT
 * Port Doctor R36S - fabriciopab, https://github.com/Fabriciopab
 * Process-local compatibility module; no Unity/game/driver code is patched.
 * The allowlisted loader caches an EGLSurface before SDL KMSDRM recreates it.
 * Only handles observed destroyed AND recreated for the SAME display/native
 * window are redirected. Other windows, contexts and NULL remain unchanged.
 */
#define _GNU_SOURCE
#include <link.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>

typedef void *(*create_fn)(void *, void *, void *, const int *);
typedef unsigned (*destroy_fn)(void *, void *);
typedef unsigned (*current_fn)(void *, void *, void *, void *);
typedef void *(*proc_fn)(const char *);
static create_fn real_create;
static destroy_fn real_destroy;
static current_fn real_current;
static proc_fn real_egl_proc, real_sdl_proc;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
struct surface { void *display, *window, *handle, *replacement; int dead; };
static struct surface surfaces[32];
static unsigned used, logged;
static uintptr_t bind_symbol(const char *, uintptr_t);

static void *redirect_locked(void *display, void *handle) {
    if (!handle) return handle;
    /* A driver can reuse an address: a live handle always takes precedence. */
    for (unsigned i=0; i<used; i++)
        if (surfaces[i].display==display && surfaces[i].handle==handle && !surfaces[i].dead)
            return handle;
    for (unsigned i=0; i<used; i++) {
        struct surface *s=&surfaces[i];
        if (s->display==display && s->handle==handle && s->dead && s->replacement) {
            for (unsigned j=0; j<used; j++)
                if (surfaces[j].display==display && surfaces[j].window==s->window &&
                    surfaces[j].handle==s->replacement && !surfaces[j].dead)
                    return s->replacement;
        }
    }
    return handle;
}
static void *wrapped_create(void *display, void *config, void *window, const int *attributes) {
    void *result=__atomic_load_n(&real_create,__ATOMIC_ACQUIRE)(display,config,window,attributes);
    if (!result) return result;
    pthread_mutex_lock(&lock);
    /* Bounded table: an untracked creation is passed through, never guessed. */
    if (used<32) {
        for (unsigned i=0; i<used; i++)
            if (surfaces[i].display==display && surfaces[i].window==window && surfaces[i].dead)
                surfaces[i].replacement=result;
        surfaces[used++]=(struct surface){display,window,result,NULL,0};
    }
    pthread_mutex_unlock(&lock);
    return result;
}
static unsigned wrapped_destroy(void *display, void *handle) {
    unsigned result=__atomic_load_n(&real_destroy,__ATOMIC_ACQUIRE)(display,handle);
    if (result) {
        pthread_mutex_lock(&lock);
        for (unsigned i=0; i<used; i++)
            if (surfaces[i].display==display && surfaces[i].handle==handle)
                surfaces[i].dead=1;
        pthread_mutex_unlock(&lock);
    }
    return result;
}
static unsigned wrapped_current(void *display, void *draw, void *read, void *context) {
    void *new_draw=draw, *new_read=read;
    int report=0;
    if (context) {
        pthread_mutex_lock(&lock);
        new_draw=redirect_locked(display,draw);
        new_read=redirect_locked(display,read);
        if ((new_draw!=draw || new_read!=read) && logged++<4) report=1;
        pthread_mutex_unlock(&lock);
    }
    unsigned result=__atomic_load_n(&real_current,__ATOMIC_ACQUIRE)(display,new_draw,new_read,context);
    if (report) {
        const char *message=result ? "Port Doctor: superfície EGL atualizada; contexto de vídeo ativo.\n"
            : "Port Doctor: superfície EGL atualizada, mas o contexto ainda falhou.\n";
        (void)write(STDERR_FILENO,message,strlen(message));
    }
    return result;
}
static void *wrapped_egl_proc(const char *name) {
    return (void *)bind_symbol(name,(uintptr_t)__atomic_load_n(&real_egl_proc,__ATOMIC_ACQUIRE)(name));
}
static void *wrapped_sdl_proc(const char *name) {
    return (void *)bind_symbol(name,(uintptr_t)__atomic_load_n(&real_sdl_proc,__ATOMIC_ACQUIRE)(name));
}
static uintptr_t bind_symbol(const char *name,uintptr_t address) {
    if (!name || !address) return address;
#define HOOK(symbol,original,replacement) \
    if (!strcmp(name,symbol)) { \
        if (address!=(uintptr_t)&replacement) \
            __atomic_store_n(&original,(__typeof__(original))address,__ATOMIC_RELEASE); \
        return (uintptr_t)&replacement; \
    }
    HOOK("eglCreateWindowSurface",real_create,wrapped_create)
    HOOK("eglDestroySurface",real_destroy,wrapped_destroy)
    HOOK("eglMakeCurrent",real_current,wrapped_current)
    HOOK("eglGetProcAddress",real_egl_proc,wrapped_egl_proc)
    HOOK("SDL_GL_GetProcAddress",real_sdl_proc,wrapped_sdl_proc)
#undef HOOK
    return address;
}
unsigned int la_version(unsigned int version) { return version>=LAV_CURRENT ? LAV_CURRENT : 0; }
unsigned int la_objopen(struct link_map *map,Lmid_t namespace_id,uintptr_t *cookie) {
    (void)map; (void)namespace_id; (void)cookie;
    return LA_FLG_BINDTO|LA_FLG_BINDFROM;
}
uintptr_t la_symbind64(Elf64_Sym *symbol,unsigned int index,uintptr_t *ref,uintptr_t *def,
                     unsigned int *flags,const char *name) {
    (void)index; (void)ref; (void)def; (void)flags;
    return bind_symbol(name,symbol->st_value);
}
