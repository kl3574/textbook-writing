#include <vector>

// Returns the index of x in sorted vector a, or -1 if absent.
int binary_search(const std::vector<int>& a, int x) {
    int lo = 0, hi = (int)a.size() - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (a[mid] == x) return mid;
        if (a[mid] < x)  lo = mid + 1;
        else             hi = mid - 1;
    }
    return -1;
}

