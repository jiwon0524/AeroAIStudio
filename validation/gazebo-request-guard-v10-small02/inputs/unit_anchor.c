#define _GNU_SOURCE
#include <unistd.h>
#include <signal.h>
/* Compile-only target-unit anchor, supplied to manager as a verified sealed
 * executable FD. No marker, loader library, work or resource-limit change.
 * Manager keeps unit active via RemainAfterExit after the owned child attaches. */
int main(void) {
    if(close_range(3,~0U,0)||raise(SIGSTOP))return 78;
    return 0;
}
