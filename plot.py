import pandas as pd
import matplotlib.pyplot as plt

# Read original strikes and mid IVs
original_data = pd.read_csv('original_strikes_mid_iv.csv')
original_strikes = original_data['Strike']
mid_ivs = original_data['IV']

# Read new strikes and interpolated IVs
interpolated_data = pd.read_csv('interpolated_strikes_iv.csv')
new_strikes = interpolated_data['Strike']
interpolated_ivs = interpolated_data['IV']

# Plot the data
plt.figure(figsize=(10, 6))

# Plot original strikes and mid IVs as points
plt.scatter(original_strikes, mid_ivs, color='red', label='Original Mid IVs', zorder=5)

# Plot interpolated strikes and interpolated IVs as a line
plt.plot(new_strikes, interpolated_ivs, color='blue', label='Interpolated IVs', zorder=3)

# Adding labels and legend
plt.title('Original and Interpolated IVs')
plt.xlabel('Strike Price')
plt.ylabel('Implied Volatility')
plt.legend()
plt.grid(True)

# Show plot
plt.show()
