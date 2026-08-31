/* SPDX-License-Identifier: MIT - deterministic tests, no EGL/GPU required. */
#include "unity_egl_rebind.c"
#include <assert.h>
#include <stdio.h>
static void *next_handle,*seen_draw,*seen_read,*seen_context;
static unsigned destroy_ok=1,current_ok=1;
static void *fake_create(void *d,void *c,void *w,const int *a) {
    (void)d;(void)c;(void)w;(void)a; return next_handle;
}
static unsigned fake_destroy(void *d,void *s) { (void)d;(void)s; return destroy_ok; }
static unsigned fake_current(void *d,void *s,void *r,void *c) {
    (void)d;seen_draw=s;seen_read=r;seen_context=c;return current_ok;
}
#define P(n) ((void *)(uintptr_t)(n))
int main(void) {
    real_create=fake_create;real_destroy=fake_destroy;real_current=fake_current;
    next_handle=P(10);assert(wrapped_create(P(1),NULL,P(2),NULL)==P(10));
    wrapped_current(P(1),P(10),P(10),P(3));assert(seen_draw==P(10));
    destroy_ok=0;wrapped_destroy(P(1),P(10));assert(!surfaces[0].dead);
    destroy_ok=1;wrapped_destroy(P(1),P(10));assert(surfaces[0].dead);
    next_handle=NULL;wrapped_create(P(1),NULL,P(2),NULL);assert(used==1);
    next_handle=P(11);wrapped_create(P(1),NULL,P(20),NULL);
    wrapped_current(P(1),P(10),P(10),P(3));assert(seen_draw==P(10)); /* other window */
    next_handle=P(12);wrapped_create(P(1),NULL,P(2),NULL);
    assert(wrapped_current(P(1),P(10),P(10),P(3))==1);
    assert(seen_draw==P(12) && seen_read==P(12) && seen_context==P(3));
    wrapped_current(P(9),P(10),P(10),P(3));assert(seen_draw==P(10)); /* other display */
    wrapped_current(P(1),NULL,NULL,NULL);assert(!seen_draw && !seen_context);
    wrapped_current(P(1),P(10),P(10),NULL);assert(seen_draw==P(10)); /* invalid unbind untouched */
    wrapped_destroy(P(1),P(12));
    wrapped_current(P(1),P(10),P(10),P(3));assert(seen_draw==P(10)); /* no live replacement */
    next_handle=P(13);wrapped_create(P(1),NULL,P(2),NULL);
    wrapped_current(P(1),P(10),P(12),P(3));assert(seen_draw==P(13) && seen_read==P(13));
    wrapped_destroy(P(1),P(13));next_handle=P(10);wrapped_create(P(1),NULL,P(2),NULL);
    wrapped_current(P(1),P(10),P(10),P(3));assert(seen_draw==P(10)); /* recycled address */
    current_ok=0;assert(!wrapped_current(P(1),P(10),P(10),P(3))); /* don't invent success */
    assert(bind_symbol("unrelated",1234)==1234 && bind_symbol("eglMakeCurrent",0)==0);
    assert(bind_symbol("eglMakeCurrent",(uintptr_t)fake_current)==(uintptr_t)wrapped_current);
    assert(bind_symbol("eglMakeCurrent",(uintptr_t)wrapped_current)==(uintptr_t)wrapped_current);
    assert(real_current==fake_current);
    puts("unity EGL: lifecycle, failure, isolation and binding tests OK");
}
