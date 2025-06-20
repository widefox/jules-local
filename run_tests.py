import unittest
import os

def run_all_tests():
    """Discovers and runs all tests in the 'tests' directory."""
    # Start discovery from the directory containing this script (project root)
    # and look for tests in the 'tests' subdirectory.
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir='tests', pattern='test_*.py')

    runner = unittest.TextTestRunner(verbosity=2) #verbosity=2 for more detailed output
    result = runner.run(suite)

    return result

if __name__ == '__main__':
    print("Discovering and running all tests...")
    test_result = run_all_tests()

    if test_result.wasSuccessful():
        print("\nAll tests passed successfully!")
        exit(0)
    else:
        print("\nSome tests failed.")
        # The number of failures/errors is implicitly printed by TextTestRunner
        exit(1) # Exit with non-zero code if tests failed
